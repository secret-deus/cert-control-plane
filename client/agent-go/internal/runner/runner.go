package runner

import (
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
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
		key, err := crypto.GenerateKeyPair(3072)
		if err != nil {
			return "", fmt.Errorf("failed to generate key: %w", err)
		}
		if err := crypto.SavePrivateKey(key, keyPath); err != nil {
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

	var resp *client.RegisterResponse
	for {
		var err error
		resp, err = r.client.Register(fingerprint)
		if err == nil {
			break
		}
		if !isRetryableRegistrationError(err) {
			return fmt.Errorf("registration request failed: %w", err)
		}
		r.logger.Warn("Registration request failed, retrying",
			zap.Duration("retry_after", r.config.PollInterval),
			zap.Error(err),
		)
		time.Sleep(r.config.PollInterval)
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

func isRetryableRegistrationError(err error) bool {
	var statusErr *client.HTTPStatusError
	if !errors.As(err, &statusErr) {
		return true
	}
	return statusErr.StatusCode == http.StatusRequestTimeout ||
		statusErr.StatusCode == http.StatusTooManyRequests ||
		statusErr.StatusCode >= http.StatusInternalServerError
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
		notAfter, err := readCertNotAfter(entry.LocalPath)
		if err != nil {
			r.logger.Warn("Failed to read cert not_after",
				zap.String("path", entry.LocalPath),
				zap.Error(err))
		} else if notAfter != "" {
			check.CurrentNotAfter = &notAfter
			r.logger.Info("Current cert not_after",
				zap.String("path", entry.LocalPath),
				zap.String("not_after", notAfter))
		}

		checks = append(checks, check)
	}

	r.logger.Info("Fetching certs from control plane", zap.Int("count", len(checks)))
	resp, err := r.client.FetchCerts(checks)
	if err != nil {
		return fmt.Errorf("fetch-certs request failed: %w", err)
	}

	r.logger.Info("Fetch-certs response", zap.Int("updates_count", len(resp.Updates)))
	for i, update := range resp.Updates {
		r.logger.Info("Update result",
			zap.Int("index", i),
			zap.String("path", update.LocalPath),
			zap.Bool("has_update", update.HasUpdate),
			zap.Any("not_after", update.NotAfter))
		if !update.HasUpdate {
			r.logger.Info("No update needed", zap.String("path", update.LocalPath))
			continue
		}
		r.logger.Info("Cert update available, deploying", zap.String("path", update.LocalPath))
		if err := r.deployCertUpdate(update); err != nil {
			r.logger.Error("Failed to deploy cert", zap.String("path", update.LocalPath), zap.Error(err))
		} else {
			r.logger.Info("Cert deployed successfully", zap.String("path", update.LocalPath))
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
	keyPath, chainPath := certSiblingPaths(certPath)

	// Backup existing files
	certBackup := backupFile(certPath)
	keyBackup := backupFile(keyPath)
	chainBackup := backupFile(chainPath)

	// Write new files
	if err := os.MkdirAll(filepath.Dir(certPath), 0755); err != nil {
		return err
	}

	if update.CertPEM != nil {
		if err := os.WriteFile(certPath, []byte(fullchainPEM(*update.CertPEM, update.ChainPEM)), 0644); err != nil {
			restoreBackups(certBackup, keyBackup, chainBackup)
			return fmt.Errorf("failed to write cert: %w", err)
		}
	}

	if update.KeyPEM != nil {
		if err := os.WriteFile(keyPath, []byte(*update.KeyPEM), 0600); err != nil {
			restoreBackups(certBackup, keyBackup, chainBackup)
			return fmt.Errorf("failed to write key: %w", err)
		}
	}

	if err := os.Remove(chainPath); err != nil && !os.IsNotExist(err) {
		restoreBackups(certBackup, keyBackup, chainBackup)
		return fmt.Errorf("failed to remove chain sidecar: %w", err)
	}

	// Reload nginx
	if r.config.NginxReloadCmd != "" {
		cmd := exec.Command("sh", "-c", r.config.NginxReloadCmd)
		if output, err := cmd.CombinedOutput(); err != nil {
			restoreBackups(certBackup, keyBackup, chainBackup)
			return fmt.Errorf("nginx reload failed: %w - %s", err, string(output))
		}
		r.logger.Info("Nginx reloaded")
	}

	// Clean up backups
	cleanupBackups(certBackup, keyBackup, chainBackup)

	r.logger.Info("Cert deployed", zap.String("path", certPath))

	// Report to control plane
	if update.CertPEM != nil {
		reportItem := client.ReportCertItem{
			LocalPath: certPath,
			CertPEM:   *update.CertPEM,
		}
		if update.ChainPEM != nil {
			reportItem.ChainPEM = update.ChainPEM
		}
		if _, err := r.client.ReportCerts([]client.ReportCertItem{reportItem}); err != nil {
			r.logger.Warn("Failed to report cert to control plane", zap.Error(err))
		} else {
			r.logger.Info("Cert reported to control plane", zap.String("path", certPath))
		}
	}

	return nil
}

func certSiblingPaths(certPath string) (string, string) {
	ext := filepath.Ext(certPath)
	base := certPath
	if ext != "" {
		base = certPath[:len(certPath)-len(ext)]
	}
	return base + ".key", base + ".chain.crt"
}

func fullchainPEM(certPEM string, chainPEM *string) string {
	fullchain := strings.TrimSpace(certPEM) + "\n"
	if chainPEM == nil {
		return fullchain
	}
	return fullchain + strings.TrimSpace(*chainPEM) + "\n"
}

type fileBackup struct {
	target string
	backup string
	mode   os.FileMode
	exists bool
}

func backupFile(path string) fileBackup {
	backup := fileBackup{
		target: path,
		backup: path + ".old",
	}
	info, err := os.Stat(path)
	if err != nil {
		return backup
	}
	backup.exists = true
	backup.mode = info.Mode().Perm()
	_ = copyFile(path, backup.backup)
	_ = os.Chmod(backup.backup, backup.mode)
	return backup
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}

func restoreBackups(backups ...fileBackup) {
	for _, backup := range backups {
		restoreBackup(backup)
	}
}

func restoreBackup(backup fileBackup) {
	if backup.exists {
		if _, err := os.Stat(backup.backup); err == nil {
			_ = copyFile(backup.backup, backup.target)
			_ = os.Chmod(backup.target, backup.mode)
			_ = os.Remove(backup.backup)
		}
		return
	}
	_ = os.Remove(backup.target)
}

func cleanupBackups(backups ...fileBackup) {
	for _, backup := range backups {
		_ = os.Remove(backup.backup)
	}
}
