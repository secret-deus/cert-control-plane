mod client;
mod config;
mod crypto;
mod runner;

use anyhow::Result;
use tracing::{error, info};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("cert-agent (Rust) starting");

    let config = config::AgentConfig::load()?;
    let runner = runner::Runner::new(config);

    if let Err(e) = runner.run().await {
        error!(error = %e, "Agent exited with error");
        std::process::exit(1);
    }

    Ok(())
}
