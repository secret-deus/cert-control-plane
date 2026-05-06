package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config holds all configuration for the agent
type Config struct {
	// Control plane connection
	ControlPlaneURL string `mapstructure:"cp_url"`

	// Agent identity
	AgentName  string `mapstructure:"name"`
	AgentToken string `mapstructure:"agent_token"`

	// CertTable: list of {local_path, cert_name} objects
	// Agent reads local certs and compares not_after with the platform
	CertTable []CertTableEntry `mapstructure:"cert_table"`

	// AutoDetect enables automatic nginx SSL certificate path detection
	// When true and cert_table is empty, agent will auto-detect from running nginx
	AutoDetect bool `mapstructure:"auto_detect"`

	// InsecureSkipVerify skips TLS certificate verification (for testing only)
	InsecureSkipVerify bool `mapstructure:"insecure_skip_verify"`

	// Local state
	StateDir string `mapstructure:"state_dir"`

	// nginx deployment
	NginxCertDir   string `mapstructure:"nginx_cert_dir"`
	NginxReloadCmd string `mapstructure:"nginx_reload_cmd"`

	// Timing
	HeartbeatInterval time.Duration `mapstructure:"heartbeat_interval"`
	PollInterval      time.Duration `mapstructure:"poll_interval"`
}

// CertTableEntry is one entry in the cert table
type CertTableEntry struct {
	LocalPath string `mapstructure:"local_path" json:"local_path"`
	CertName  string `mapstructure:"cert_name" json:"cert_name,omitempty"`
}

// DefaultConfig returns default configuration
func DefaultConfig() *Config {
	return &Config{
		AutoDetect:        true, // Enable auto-detection by default
		StateDir:          "/var/lib/cert-agent",
		NginxCertDir:      "/etc/nginx/certs",
		NginxReloadCmd:    "nginx -s reload",
		HeartbeatInterval: 30 * time.Second,
		PollInterval:      5 * time.Second,
	}
}

// Load reads configuration from file and environment variables
func Load(configPath string) (*Config, error) {
	cfg := DefaultConfig()

	viper.SetDefault("auto_detect", cfg.AutoDetect)
	viper.SetDefault("state_dir", cfg.StateDir)
	viper.SetDefault("nginx_cert_dir", cfg.NginxCertDir)
	viper.SetDefault("nginx_reload_cmd", cfg.NginxReloadCmd)
	viper.SetDefault("heartbeat_interval", cfg.HeartbeatInterval)
	viper.SetDefault("poll_interval", cfg.PollInterval)

	viper.SetEnvPrefix("CERT_AGENT")
	viper.AutomaticEnv()
	for _, key := range []string{
		"cp_url",
		"name",
		"agent_token",
		"auto_detect",
		"insecure_skip_verify",
		"state_dir",
		"nginx_cert_dir",
		"nginx_reload_cmd",
		"heartbeat_interval",
		"poll_interval",
	} {
		if err := viper.BindEnv(key); err != nil {
			return nil, fmt.Errorf("failed to bind env %s: %w", key, err)
		}
	}

	if configPath != "" {
		viper.SetConfigFile(configPath)
	} else {
		viper.SetConfigName("agent")
		viper.SetConfigType("yaml")
		viper.AddConfigPath("/etc/cert-agent/")
		viper.AddConfigPath(".")
	}

	if err := viper.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config: %w", err)
		}
	}

	if err := viper.Unmarshal(cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}
	if raw := strings.TrimSpace(os.Getenv("CERT_AGENT_CERT_TABLE")); raw != "" {
		var certTable []CertTableEntry
		if err := json.Unmarshal([]byte(raw), &certTable); err != nil {
			return nil, fmt.Errorf("failed to parse CERT_AGENT_CERT_TABLE: %w", err)
		}
		cfg.CertTable = certTable
	}

	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	// Try loading agent_token from disk if not in config/env
	if cfg.AgentToken == "" {
		tokenPath := filepath.Join(cfg.StateDir, "agent_token")
		if data, err := os.ReadFile(tokenPath); err == nil {
			cfg.AgentToken = string(data)
		}
	}

	return cfg, nil
}

// Validate checks if configuration is valid
func (c *Config) Validate() error {
	if c.ControlPlaneURL == "" {
		return fmt.Errorf("cp_url is required")
	}
	if c.AgentName == "" {
		return fmt.Errorf("name is required")
	}
	return nil
}

// IsRegistered checks if agent has a persisted agent_token
func (c *Config) IsRegistered() bool {
	if c.AgentToken != "" {
		return true
	}
	_, err := os.Stat(c.AgentTokenPath())
	return err == nil
}

// KeyPath returns path to agent private key
func (c *Config) KeyPath() string {
	return filepath.Join(c.StateDir, "agent.key")
}

// AgentIDPath returns path to agent ID file
func (c *Config) AgentIDPath() string {
	return filepath.Join(c.StateDir, "agent_id")
}

// AgentTokenPath returns path to agent token file
func (c *Config) AgentTokenPath() string {
	return filepath.Join(c.StateDir, "agent_token")
}

// RunAutoDetect populates CertTable by auto-detecting nginx SSL certificate paths
// This should be called after config is loaded but before agent starts
func (c *Config) RunAutoDetect() error {
	if !c.AutoDetect || len(c.CertTable) > 0 {
		return nil
	}

	// Import nginx detector only when needed
	// This creates a dependency, but keeps config package clean
	return nil // Actual detection is done in main
}
