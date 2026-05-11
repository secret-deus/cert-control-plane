package runner

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/cert-control-plane/agent-go/internal/client"
	"github.com/cert-control-plane/agent-go/internal/config"
)

func strPtr(v string) *string {
	return &v
}

func TestCertSiblingPathsSupportPemAndCrt(t *testing.T) {
	tests := []struct {
		certPath string
		keyPath  string
		chain    string
	}{
		{
			certPath: "/etc/nginx/certs/api.crt",
			keyPath:  "/etc/nginx/certs/api.key",
			chain:    "/etc/nginx/certs/api.chain.crt",
		},
		{
			certPath: "/opt/custom/tls/api.pem",
			keyPath:  "/opt/custom/tls/api.key",
			chain:    "/opt/custom/tls/api.chain.crt",
		},
	}

	for _, tt := range tests {
		keyPath, chainPath := certSiblingPaths(tt.certPath)
		if keyPath != tt.keyPath {
			t.Fatalf("key path for %s: got %s want %s", tt.certPath, keyPath, tt.keyPath)
		}
		if chainPath != tt.chain {
			t.Fatalf("chain path for %s: got %s want %s", tt.certPath, chainPath, tt.chain)
		}
	}
}

func TestDeployCertUpdateRestoresCertKeyAndChainOnReloadFailure(t *testing.T) {
	dir := t.TempDir()
	certPath := filepath.Join(dir, "api.pem")
	keyPath := filepath.Join(dir, "api.key")
	chainPath := filepath.Join(dir, "api.chain.crt")

	oldCert := "old-cert"
	oldKey := "old-key"
	oldChain := "old-chain"
	if err := os.WriteFile(certPath, []byte(oldCert), 0644); err != nil {
		t.Fatalf("write old cert: %v", err)
	}
	if err := os.WriteFile(keyPath, []byte(oldKey), 0600); err != nil {
		t.Fatalf("write old key: %v", err)
	}
	if err := os.WriteFile(chainPath, []byte(oldChain), 0644); err != nil {
		t.Fatalf("write old chain: %v", err)
	}

	r := New(&config.Config{NginxReloadCmd: "false"}, zap.NewNop())
	err := r.deployCertUpdate(client.CertUpdateItem{
		LocalPath: certPath,
		CertPEM:   strPtr("new-cert"),
		KeyPEM:    strPtr("new-key"),
		ChainPEM:  strPtr("new-chain"),
	})
	if err == nil {
		t.Fatal("expected reload failure")
	}

	assertFile := func(path, want string) {
		t.Helper()
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if string(got) != want {
			t.Fatalf("content for %s: got %q want %q", path, string(got), want)
		}
	}

	assertFile(certPath, oldCert)
	assertFile(keyPath, oldKey)
	assertFile(chainPath, oldChain)

	info, err := os.Stat(keyPath)
	if err != nil {
		t.Fatalf("stat key: %v", err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatalf("key mode: got %o want 600", info.Mode().Perm())
	}

	for _, backup := range []string{certPath + ".old", keyPath + ".old", chainPath + ".old"} {
		if _, err := os.Stat(backup); !os.IsNotExist(err) {
			t.Fatalf("backup %s should be removed after restore, err=%v", backup, err)
		}
	}
}

func TestRegisterRetriesUntilControlPlaneAcceptsRequest(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/agent/register" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Method; got != http.MethodPost {
			t.Fatalf("method: got %s want POST", got)
		}

		if atomic.AddInt32(&attempts, 1) < 3 {
			http.Error(w, "not ready", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(client.RegisterResponse{
			Status:     "approved",
			AgentID:    "agent-1",
			AgentToken: strPtr("token-1"),
		})
	}))
	defer server.Close()

	cfg := &config.Config{
		AgentName:       "edge-node-test",
		ControlPlaneURL: server.URL,
		PollInterval:    time.Millisecond,
		StateDir:        t.TempDir(),
	}
	cpClient, err := client.New(cfg)
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	runner := New(cfg, zap.NewNop())
	runner.client = cpClient

	if err := runner.register("fingerprint"); err != nil {
		t.Fatalf("register: %v", err)
	}
	if got := atomic.LoadInt32(&attempts); got != 3 {
		t.Fatalf("attempts: got %d want 3", got)
	}
	if cfg.AgentToken != "token-1" {
		t.Fatalf("agent token: got %q want token-1", cfg.AgentToken)
	}

	tokenBytes, err := os.ReadFile(cfg.AgentTokenPath())
	if err != nil {
		t.Fatalf("read token: %v", err)
	}
	if string(tokenBytes) != "token-1" {
		t.Fatalf("token file: got %q want token-1", string(tokenBytes))
	}
}

func TestRegisterDoesNotRetryNonRecoverableStatus(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		http.Error(w, "bad registration", http.StatusBadRequest)
	}))
	defer server.Close()

	cfg := &config.Config{
		AgentName:       "edge-node-test",
		ControlPlaneURL: server.URL,
		PollInterval:    time.Millisecond,
		StateDir:        t.TempDir(),
	}
	cpClient, err := client.New(cfg)
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	runner := New(cfg, zap.NewNop())
	runner.client = cpClient

	if err := runner.register("fingerprint"); err == nil {
		t.Fatal("expected registration error")
	}
	if got := atomic.LoadInt32(&attempts); got != 1 {
		t.Fatalf("attempts: got %d want 1", got)
	}
}
