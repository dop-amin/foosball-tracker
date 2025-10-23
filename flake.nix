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
        python = pkgs.python311;
        pythonPackages = python.pkgs;

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

            # Create wrapper script
            cat > $out/bin/foosball-tracker <<EOF
            #!${pkgs.bash}/bin/bash
            cd $out/share/foosball-tracker
            ${python}/bin/python -m flask db upgrade
            ${python}/bin/python recalculate_elo.py
            exec ${python}/bin/python app.py "\$@"
            EOF
            chmod +x $out/bin/foosball-tracker
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
                WorkingDirectory = "${cfg.package}/share/foosball-tracker";
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
                  mkdir -p ${cfg.dataDir}/instance
                  ln -sf ${cfg.dataDir}/foosball.db ${cfg.package}/share/foosball-tracker/instance/foosball.db || true

                  # Run database migrations
                  cd ${cfg.package}/share/foosball-tracker
                  ${pkgs.python311}/bin/python -m flask db upgrade

                  # Recalculate ELO ratings
                  ${pkgs.python311}/bin/python ${cfg.package}/share/foosball-tracker/recalculate_elo.py
                '';

                ExecStart = "${pkgs.python311}/bin/python ${cfg.package}/share/foosball-tracker/app.py";

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
