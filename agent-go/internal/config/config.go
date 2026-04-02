package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"time"

	"github.com/mitchellh/mapstructure"
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
	CertName  string `mapstructure:"cert_name" json:"cert_name"`
}

// DefaultConfig returns default configuration
func DefaultConfig() *Config {
	return &Config{
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

	viper.SetDefault("state_dir", cfg.StateDir)
	viper.SetDefault("nginx_cert_dir", cfg.NginxCertDir)
	viper.SetDefault("nginx_reload_cmd", cfg.NginxReloadCmd)
	viper.SetDefault("heartbeat_interval", cfg.HeartbeatInterval)
	viper.SetDefault("poll_interval", cfg.PollInterval)

	viper.SetEnvPrefix("CERT_AGENT")
	viper.AutomaticEnv()

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

	if err := viper.Unmarshal(
		cfg,
		viper.DecodeHook(
			mapstructure.ComposeDecodeHookFunc(durationDecodeHook()),
		),
	); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	// Environment variables are the primary deployment model for the current agent.
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_CP_URL")); value != "" {
		cfg.ControlPlaneURL = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_NAME")); value != "" {
		cfg.AgentName = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_TOKEN")); value != "" {
		cfg.AgentToken = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_STATE_DIR")); value != "" {
		cfg.StateDir = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_NGINX_CERT_DIR")); value != "" {
		cfg.NginxCertDir = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_NGINX_RELOAD_CMD")); value != "" {
		cfg.NginxReloadCmd = value
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_HEARTBEAT_INTERVAL")); value != "" {
		seconds, err := parseInterval(value)
		if err != nil {
			return nil, fmt.Errorf("invalid CERT_AGENT_HEARTBEAT_INTERVAL: %w", err)
		}
		cfg.HeartbeatInterval = seconds
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_POLL_INTERVAL")); value != "" {
		seconds, err := parseInterval(value)
		if err != nil {
			return nil, fmt.Errorf("invalid CERT_AGENT_POLL_INTERVAL: %w", err)
		}
		cfg.PollInterval = seconds
	}
	if value := strings.TrimSpace(os.Getenv("CERT_AGENT_CERT_TABLE")); value != "" {
		var certTable []CertTableEntry
		if err := json.Unmarshal([]byte(value), &certTable); err != nil {
			return nil, fmt.Errorf("invalid CERT_AGENT_CERT_TABLE JSON: %w", err)
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
			cfg.AgentToken = strings.TrimSpace(string(data))
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

func parseInterval(value string) (time.Duration, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return 0, nil
	}
	if duration, err := time.ParseDuration(value); err == nil {
		return duration, nil
	}
	seconds, err := strconv.Atoi(value)
	if err != nil {
		return 0, err
	}
	return time.Duration(seconds) * time.Second, nil
}

func durationDecodeHook() mapstructure.DecodeHookFuncType {
	durationType := reflect.TypeOf(time.Duration(0))
	return func(from reflect.Type, to reflect.Type, data interface{}) (interface{}, error) {
		if to != durationType {
			return data, nil
		}

		switch value := data.(type) {
		case string:
			return parseInterval(value)
		case int:
			return time.Duration(value) * time.Second, nil
		case int64:
			return time.Duration(value) * time.Second, nil
		case float64:
			return time.Duration(int(value)) * time.Second, nil
		default:
			return data, nil
		}
	}
}
