# NixOS Deployment Guide

This document explains how to deploy Foosball Tracker on NixOS using the provided Nix flake.

## Quick Start

### 1. Enable Flakes

Ensure flakes are enabled in your NixOS configuration:

```nix
{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
}
```

### 2. Add to NixOS Configuration

Add the foosball-tracker flake to your system configuration. In your `/etc/nixos/configuration.nix` or flake-based configuration:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    foosball-tracker.url = "path:/path/to/foosball-tracker";
    # Or from git:
    # foosball-tracker.url = "github:yourusername/foosball-tracker";
  };

  outputs = { self, nixpkgs, foosball-tracker, ... }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      modules = [
        foosball-tracker.nixosModules.default
        {
          services.foosball-tracker = {
            enable = true;
            host = "0.0.0.0";
            port = 5000;
          };
        }
      ];
    };
  };
}
```

### 3. Rebuild and Start

```bash
sudo nixos-rebuild switch
```

The service will automatically start and be available at `http://localhost:5000`.

## Configuration Options

The following options are available under `services.foosball-tracker`:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | bool | `false` | Enable the Foosball Tracker service |
| `package` | package | `self.packages.default` | The foosball-tracker package to use |
| `host` | string | `"127.0.0.1"` | Host address to bind to |
| `port` | port | `5000` | Port to listen on |
| `dataDir` | path | `"/var/lib/foosball-tracker"` | Directory for SQLite database |
| `user` | string | `"foosball-tracker"` | User account for the service |
| `group` | string | `"foosball-tracker"` | Group for the service |

## Example Configurations

### Basic Configuration (Local Access Only)

```nix
services.foosball-tracker = {
  enable = true;
};
```

### Public-Facing Configuration with Nginx

```nix
services.foosball-tracker = {
  enable = true;
  host = "127.0.0.1";
  port = 5000;
};

services.nginx = {
  enable = true;
  virtualHosts."foosball.example.com" = {
    enableACME = true;
    forceSSL = true;
    locations."/" = {
      proxyPass = "http://127.0.0.1:5000";
      proxyWebsockets = true;
      extraConfig = ''
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
      '';
    };
  };
};

security.acme = {
  acceptTerms = true;
  defaults.email = "your-email@example.com";
};

networking.firewall.allowedTCPPorts = [ 80 443 ];
```

### Custom Data Directory

```nix
services.foosball-tracker = {
  enable = true;
  dataDir = "/srv/foosball-tracker";
};
```

## Service Management

### Check Service Status

```bash
systemctl status foosball-tracker
```

### View Logs

```bash
journalctl -u foosball-tracker -f
```

### Restart Service

```bash
sudo systemctl restart foosball-tracker
```

### Stop Service

```bash
sudo systemctl stop foosball-tracker
```

## Development Shell

For development purposes, you can enter a Nix shell with all dependencies:

```bash
nix develop
python app.py
```

Or run directly:

```bash
nix run .
```

## Database Location

The SQLite database is stored in the configured `dataDir` (default: `/var/lib/foosball-tracker/foosball.db`).

### Backup Database

```bash
sudo cp /var/lib/foosball-tracker/foosball.db /path/to/backup/foosball.db.backup
```

### Restore Database

```bash
sudo systemctl stop foosball-tracker
sudo cp /path/to/backup/foosball.db.backup /var/lib/foosball-tracker/foosball.db
sudo systemctl start foosball-tracker
```

## Security Considerations

1. **Secret Key**: The application automatically generates a cryptographically secure random secret key on each startup using Python's `secrets` module. No manual configuration is required.

2. **Use HTTPS**: Always deploy behind a reverse proxy (like Nginx) with SSL/TLS enabled for production use.

3. **Firewall**: The service includes security hardening options like `ProtectSystem`, `ProtectHome`, and `PrivateTmp`.

4. **Access Control**: By default, the service binds to `127.0.0.1`. Only expose to `0.0.0.0` if you understand the security implications.

## Troubleshooting

### Service Won't Start

Check the logs:
```bash
journalctl -u foosball-tracker -n 50
```

Common issues:
- Port already in use
- Database permissions
- Missing dependencies

### Database Errors

Ensure the database directory is writable:
```bash
sudo chown -R foosball-tracker:foosball-tracker /var/lib/foosball-tracker
```

### Reset Database

To start fresh:
```bash
sudo systemctl stop foosball-tracker
sudo rm /var/lib/foosball-tracker/foosball.db
sudo systemctl start foosball-tracker
```

The database will be recreated automatically on startup.
