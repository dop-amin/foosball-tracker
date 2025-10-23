{
  description = "Foosball Tracker - A web application for tracking office foosball games";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;
        pythonPackages = python.pkgs;

        # Python environment with all dependencies
        pythonEnv = python.withPackages (ps: with ps; [
          flask
          flask-sqlalchemy
          flask-migrate
          python-dateutil
        ]);

        foosball-tracker = pythonPackages.buildPythonApplication {
          pname = "foosball-tracker";
          version = "0.1.0";

          src = ./.;

          # This project doesn't use setuptools/pyproject.toml
          format = "other";

          propagatedBuildInputs = with pythonPackages; [
            flask
            flask-sqlalchemy
            flask-migrate
            python-dateutil
          ];

          # Don't run tests during build (no tests directory exists)
          doCheck = false;

          # Install application files
          installPhase = ''
            mkdir -p $out/{bin,share/foosball-tracker}

            # Copy application files
            cp -r . $out/share/foosball-tracker/

            # Remove .git and other unnecessary files
            rm -rf $out/share/foosball-tracker/.git
            rm -rf $out/share/foosball-tracker/instance

            # Migration script for systemd
            cat > $out/bin/foosball-tracker-migrate <<EOF
            #!${pkgs.bash}/bin/bash
            ${pythonEnv}/bin/python -m flask db upgrade
            ${pythonEnv}/bin/python recalculate_elo.py
            EOF
            chmod +x $out/bin/foosball-tracker-migrate

            # Run script for systemd
            cat > $out/bin/foosball-tracker-run <<EOF
            #!${pkgs.bash}/bin/bash
            exec ${pythonEnv}/bin/python app.py "\$@"
            EOF
            chmod +x $out/bin/foosball-tracker-run
          '';

          meta = with pkgs.lib; {
            description = "Web application for tracking office foosball games";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };

      in
      {
        packages = {
          default = foosball-tracker;
          foosball-tracker = foosball-tracker;
        };

        apps.default = {
          type = "app";
          program = "${foosball-tracker}/bin/foosball-tracker";
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pythonPackages; [
            flask
            flask-sqlalchemy
            flask-migrate
            python-dateutil
          ] ++ [
            python
          ];

          shellHook = ''
            echo "Foosball Tracker development environment"
            echo "Run 'python app.py' to start the application"
          '';
        };
      }
    ) // {
      nixosModules.default = { config, lib, pkgs, ... }:
        with lib;
        let
          cfg = config.services.foosball-tracker;
        in
        {
          options.services.foosball-tracker = {
            enable = mkEnableOption "Foosball Tracker service";

            package = mkOption {
              type = types.package;
              default = self.packages.${pkgs.system}.default;
              description = "The foosball-tracker package to use";
            };

            host = mkOption {
              type = types.str;
              default = "127.0.0.1";
              description = "Host to bind to";
            };

            port = mkOption {
              type = types.port;
              default = 5000;
              description = "Port to bind to";
            };

            dataDir = mkOption {
              type = types.path;
              default = "/var/lib/foosball-tracker";
              description = "Directory to store the SQLite database";
            };

            user = mkOption {
              type = types.str;
              default = "foosball-tracker";
              description = "User account under which foosball-tracker runs";
            };

            group = mkOption {
              type = types.str;
              default = "foosball-tracker";
              description = "Group under which foosball-tracker runs";
            };
          };

          config = mkIf cfg.enable {
            systemd.services.foosball-tracker = {
              description = "Foosball Tracker Web Application";
              after = [ "network.target" ];
              wantedBy = [ "multi-user.target" ];

              serviceConfig = {
                Type = "simple";
                User = cfg.user;
                Group = cfg.group;
                WorkingDirectory = cfg.dataDir;
                StateDirectory = "foosball-tracker";
                StateDirectoryMode = "0750";

                # Security hardening
                PrivateTmp = true;
                ProtectSystem = "strict";
                ProtectHome = true;
                NoNewPrivileges = true;
                ReadWritePaths = cfg.dataDir;

                # Environment variables
                Environment = [
                  "DATABASE_PATH=${cfg.dataDir}/foosball.db"
                ];

                ExecStartPre = pkgs.writeShellScript "foosball-tracker-pre" ''
                  # Run database migrations
                  ${cfg.package}/bin/foosball-tracker-migrate
                '';

                ExecStart = "${cfg.package}/bin/foosball-tracker-run";

                Restart = "on-failure";
                RestartSec = "5s";
              };
            };

            users.users.${cfg.user} = mkIf (cfg.user == "foosball-tracker") {
              isSystemUser = true;
              group = cfg.group;
              description = "Foosball Tracker service user";
              home = cfg.dataDir;
              createHome = true;
            };

            users.groups.${cfg.group} = mkIf (cfg.group == "foosball-tracker") {};
          };
        };
    };
}
