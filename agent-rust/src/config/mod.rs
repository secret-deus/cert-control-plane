use std::path::PathBuf;
use serde::{Deserialize, Serialize};

/// Entry in the cert_table: maps a local filesystem path to a named certificate
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CertTableEntry {
    /// Absolute path where the certificate should be deployed, e.g. /etc/nginx/ssl/api.crt
    pub local_path: String,
    /// Human-readable label for this entry (matches cert name in control plane)
    pub cert_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    /// Control plane base URL, e.g. https://cp.example.com
    pub cp_url: String,

    /// Unique agent name (used during TOFU registration)
    pub name: String,

    /// Agent token loaded from file after approval; not set in config file
    #[serde(default)]
    pub agent_token: String,

    /// List of cert paths this agent manages
    #[serde(default)]
    pub cert_table: Vec<CertTableEntry>,

    /// State directory for storing the private key and agent token
    #[serde(default = "default_state_dir")]
    pub state_dir: PathBuf,

    /// Heartbeat interval in seconds
    #[serde(default = "default_heartbeat_interval")]
    pub heartbeat_interval: u64,

    /// Approval polling interval in seconds
    #[serde(default = "default_poll_interval")]
    pub poll_interval: u64,

    /// Shell command to reload the TLS-terminating service after cert update
    #[serde(default = "default_reload_cmd")]
    pub reload_cmd: String,
}

fn default_state_dir() -> PathBuf {
    PathBuf::from("/var/lib/cert-agent")
}

fn default_heartbeat_interval() -> u64 {
    30
}

fn default_poll_interval() -> u64 {
    5
}

fn default_reload_cmd() -> String {
    "nginx -s reload".to_string()
}

impl AgentConfig {
    /// Load configuration from file and environment variables
    pub fn load() -> anyhow::Result<Self> {
        let mut builder = config::Config::builder();

        builder = builder
            .add_source(config::File::with_name("/etc/cert-agent/agent").required(false))
            .add_source(config::File::with_name("agent").required(false))
            .add_source(
                config::Environment::with_prefix("CERT_AGENT")
                    .separator("__")
                    .try_parsing(true),
            );

        let cfg = builder.build()?;
        let mut agent_cfg: AgentConfig = cfg.try_deserialize()?;
        agent_cfg.validate()?;

        // Load persisted agent_token if the file exists and token is not set
        if agent_cfg.agent_token.is_empty() {
            if let Ok(token) = std::fs::read_to_string(agent_cfg.agent_token_path()) {
                agent_cfg.agent_token = token.trim().to_string();
            }
        }

        Ok(agent_cfg)
    }

    fn validate(&self) -> anyhow::Result<()> {
        if self.cp_url.is_empty() {
            anyhow::bail!("cp_url is required");
        }
        if self.name.is_empty() {
            anyhow::bail!("name is required");
        }
        Ok(())
    }

    /// True if a persisted agent token file exists (agent has been approved)
    pub fn is_registered(&self) -> bool {
        self.agent_token_path().exists()
    }

    /// Path to the persisted agent token
    pub fn agent_token_path(&self) -> PathBuf {
        self.state_dir.join("agent.token")
    }

    /// Path to the agent's RSA private key (identity key, not cert key)
    pub fn key_path(&self) -> PathBuf {
        self.state_dir.join("agent.key")
    }
}
