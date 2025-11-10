# Kanat Composer Quickstart

This document ships with the extracted `BackendApplication/` directory to help operators run the packaged tooling without the full repository.

## 1. Install the Bundle

1. Copy `installer.run` to the target machine.
2. Make it executable:
   ```bash
   chmod +x installer.run
   ```
3. Run the installer (optional path argument sets the base directory):
   ```bash
   ./installer.run            # extracts to ./BackendApplication/
   ./installer.run /opt       # extracts to /opt/BackendApplication/
   ```
4. Change into the extracted directory:
   ```bash
   cd BackendApplication
   ```

## 2. Launch the Composer Dashboard

- Double-click `composer` (macOS Finder / Windows Explorer) **or** run `./composer --gui` from the installation directory.
- When launched without arguments the GUI opens automatically and minimizes the originating Terminal window on macOS.
- Use the dashboard buttons to **Quick Build**, **Up**, **Stop**, **Restart**, or **Kill** the `dev`/`prod` environments. The sidebar shows live status for PacketProcessing, Postgres, QuestDB, and Seq.

## 3. Command-Line Usage (Optional)

All traditional commands remain available from the installation root:

```bash
./composer build            # Rehydrate artifacts for dev/prod
./composer up prod          # Start production environment
./composer up dev -d        # Start development detached
./composer stop prod        # Stop production containers + DLL
./composer kill dev         # Remove dev containers and artifacts
./composer status           # Show container/process status
```

Docker images are loaded automatically from the packaged tarballs when needed; internet access is not required unless pulling new images.

## 4. Maintenance Tips

- Run `./composer build` after updating packages inside `artifacts/` to regenerate DLLs and cache Docker images.
- Use `./composer kill <env>` before replacing the entire `BackendApplication/` directory with a newer installer.
- If the GUI does not launch, fall back to the CLI commands above and consult `artifacts/logs/` for service output.

For detailed deployment documentation, refer to `Composer_cli/DEPLOY_README.md` in the full KanatBackend repository.


