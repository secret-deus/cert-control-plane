package runner

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"go.uber.org/zap"

	"github.com/cert-control-plane/agent-go/internal/client"
	"github.com/cert-control-plane/agent-go/internal/config"
	"github.com/cert-control-plane/agent-go/internal/crypto"
)

// Runner manages the agent lifecycle
type Runner struct {
	config *config.Config
	logger *zap.Logger
	client *client.ControlPlaneClient
}

// New creates a new Runner
func New(cfg *config.Config, logger *zap.Logger) *Runner {
	return &Runner{
		config: cfg,
		logger: logger,
	}
}

// Run starts the agent main loop
func (r *Runner) Run() error {
	r.logger.Info("cert-agent starting",
		zap.String("name", r.config.AgentName),
		zap.String("cp", r.config.ControlPlaneURL),
	)

	// Ensure state directory exists
	if err := os.MkdirAll(r.config.StateDir, 0755); err != nil {
		return fmt.Errorf("failed to create state dir: %w", err)
	}

	// Ensure we have a key pair
	fingerprint, err := r.ensureKeyPair()
	if err != nil {
		return fmt.Errorf("failed to ensure key pair: %w", err)
	}

	// Create HTTP client (no mTLS)
	c, err := client.New(r.config)
	if err != nil {
		return fmt.Errorf("failed to create client: %w", err)
	}
	r.client = c

	// Register if needed
	if !r.config.IsRegistered() {
		if err := r.register(fingerprint); err != nil {
			return fmt.Errorf("registration failed: %w", err)
		}
	} else {
		r.logger.Info("Already registered")
	}

	return r.runMainLoop()
}

// ensureKeyPair loads or generates the RSA key pair, returning the fingerprint
func (r *Runner) ensureKeyPair() (string, error) {
	keyPath := r.config.KeyPath()

	if _, err := os.Stat(keyPath); os.IsNotExist(err) {
		r.logger.Info("Generating new key pair", zap.String("path", keyPath))
		if _, err := crypto.GenerateKeyPair(3072); err != nil {
			return "", fmt.Errorf("failed to generate key: %w", err)
		}
		if err := crypto.SavePrivateKey(nil, keyPath); err != nil {
			return "", fmt.Errorf("failed to save key: %w", err)
		}
	}

	keyPEM, err := os.ReadFile(keyPath)
	if err != nil {
		return "", fmt.Errorf("failed to read key: %w", err)
	}

	fingerprint, err := client.ComputeFingerprint(keyPEM)
	if err != nil {
		return "", fmt.Errorf("failed to compute fingerprint: %w", err)
	}

	r.logger.Info("Agent fingerprint", zap.String("fingerprint", fingerprint))
	return fingerprint, nil
}

// register performs TOFU registration and waits for admin approval
func (r *Runner) register(fingerprint string) error {
	r.logger.Info("Starting TOFU registration", zap.String("name", r.config.AgentName))

	resp, err := r.client.Register(fingerprint)
	if err != nil {
		return fmt.Errorf("registration request failed: %w", err)
	}

	r.logger.Info("Registration response",
		zap.String("status", resp.Status),
		zap.String("agent_id", resp.AgentID),
	)

	if resp.Status == "approved" && resp.AgentToken != nil {
		return r.saveToken(*resp.AgentToken)
	}

	if resp.Status == "pending" {
		return r.pollUntilApproved(resp.AgentID, fingerprint)
	}

	return fmt.Errorf("unexpected registration status: %s", resp.Status)
}

func (r *Runner) pollUntilApproved(agentID, fingerprint string) error {
	r.logger.Info("Waiting for admin approval", zap.Duration("poll_interval", r.config.PollInterval))

	for {
		resp, err := r.client.CheckRegistrationStatus(agentID, fingerprint)
		if err != nil {
			r.logger.Warn("Approval poll failed", zap.Error(err))
		} else {
			switch resp.Status {
			case "approved":
				if resp.AgentToken != nil {
					r.logger.Info("Admin approved!")
					return r.saveToken(*resp.AgentToken)
				}
			case "rejected":
				return fmt.Errorf("agent registration rejected by admin")
			default:
				r.logger.Debug("Still waiting", zap.String("status", resp.Status))
			}
		}
		time.Sleep(r.config.PollInterval)
	}
}

func (r *Runner) saveToken(token string) error {
	tokenPath := r.config.AgentTokenPath()
	if err := os.WriteFile(tokenPath, []byte(token), 0600); err != nil {
		return fmt.Errorf("failed to save agent token: %w", err)
	}
	r.config.AgentToken = token
	r.logger.Info("Agent token saved", zap.String("path", tokenPath))
	return nil
}

func (r *Runner) runMainLoop() error {
	r.logger.Info("Entering main loop",
		zap.Duration("interval", r.config.HeartbeatInterval),
		zap.Int("cert_table_size", len(r.config.CertTable)),
	)

	ticker := time.NewTicker(r.config.HeartbeatInterval)
	defer ticker.Stop()

	for {
		// Heartbeat
		if _, err := r.client.Heartbeat(); err != nil {
			r.logger.Error("Heartbeat failed", zap.Error(err))
		} else {
			r.logger.Debug("Heartbeat OK")

			// Fetch and deploy certs
			if err := r.fetchAndDeployCerts(); err != nil {
				r.logger.Error("Cert fetch/deploy failed", zap.Error(err))
			}
		}

		<-ticker.C
	}
}

func (r *Runner) fetchAndDeployCerts() error {
	if len(r.config.CertTable) == 0 {
		r.logger.Debug("cert_table is empty, nothing to check")
		return nil
	}

	// Build batch check payload
	var checks []client.CertCheckItem
	for _, entry := range r.config.CertTable {
		check := client.CertCheckItem{LocalPath: entry.LocalPath}

		// Read current cert's not_after if it exists
		if notAfter, err := readCertNotAfter(entry.LocalPath); err == nil && notAfter != "" {
			check.CurrentNotAfter = &notAfter
		}

		checks = append(checks, check)
	}

	resp, err := r.client.FetchCerts(checks)
	if err != nil {
		return fmt.Errorf("fetch-certs request failed: %w", err)
	}

	for _, update := range resp.Updates {
		if !update.HasUpdate {
			continue
		}
		r.logger.Info("Cert update available", zap.String("path", update.LocalPath))
		if err := r.deployCertUpdate(update); err != nil {
			r.logger.Error("Failed to deploy cert", zap.String("path", update.LocalPath), zap.Error(err))
		}
	}

	return nil
}

func readCertNotAfter(certPath string) (string, error) {
	data, err := os.ReadFile(certPath)
	if err != nil {
		return "", err
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return "", fmt.Errorf("failed to decode PEM")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return "", err
	}
	return cert.NotAfter.UTC().Format(time.RFC3339), nil
}

func (r *Runner) deployCertUpdate(update client.CertUpdateItem) error {
	certPath := update.LocalPath
	keyPath := replaceExt(certPath, ".crt", ".key")
	chainPath := replaceExt(certPath, ".crt", ".chain.crt")

	// Backup existing files
	oldCertPath := certPath + ".old"
	oldKeyPath := keyPath + ".old"
	_ = copyFile(certPath, oldCertPath)
	_ = copyFile(keyPath, oldKeyPath)

	// Write new files
	if err := os.MkdirAll(filepath.Dir(certPath), 0755); err != nil {
		return err
	}

	if update.CertPEM != nil {
		if err := os.WriteFile(certPath, []byte(*update.CertPEM), 0644); err != nil {
			restoreBackup(oldCertPath, certPath)
			return fmt.Errorf("failed to write cert: %w", err)
		}
	}

	if update.KeyPEM != nil {
		if err := os.WriteFile(keyPath, []byte(*update.KeyPEM), 0600); err != nil {
			restoreBackup(oldCertPath, certPath)
			return fmt.Errorf("failed to write key: %w", err)
		}
	}

	if update.ChainPEM != nil {
		if err := os.WriteFile(chainPath, []byte(*update.ChainPEM), 0644); err != nil {
			r.logger.Warn("Failed to write chain", zap.Error(err))
		}
	}

	// Reload nginx
	if r.config.NginxReloadCmd != "" {
		cmd := exec.Command("sh", "-c", r.config.NginxReloadCmd)
		if output, err := cmd.CombinedOutput(); err != nil {
			restoreBackup(oldCertPath, certPath)
			restoreBackup(oldKeyPath, keyPath)
			return fmt.Errorf("nginx reload failed: %w - %s", err, string(output))
		}
	}

	// Clean up backups
	os.Remove(oldCertPath)
	os.Remove(oldKeyPath)

	r.logger.Info("Cert deployed", zap.String("path", certPath))
	return nil
}

func replaceExt(path, oldExt, newExt string) string {
	n := len(path)
	if n >= len(oldExt) && path[n-len(oldExt):] == oldExt {
		return path[:n-len(oldExt)] + newExt
	}
	return path + newExt
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}

func restoreBackup(backup, target string) {
	if _, err := os.Stat(backup); err == nil {
		_ = copyFile(backup, target)
	}
}
