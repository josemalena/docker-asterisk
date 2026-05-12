files=("alsa.conf" "cli_aliases.conf" "features.conf" "minivm.conf" "pjsip.conf" "rtp.conf" "asterisk.conf" "console.conf" "indications.conf" "modules.conf" "pjsip_endpoint.conf" "websms.conf" "autoban.conf" "extensions.conf" "logger.conf" "musiconhold.conf" "pjsip_transport.conf" "ccss.conf" "extensions_local.conf" "manager.conf" "pjproject.conf" "pjsip_wizard.conf")
for file in "${files[@]}"; do
      docker compose cp tele:/srv/etc/asterisk/$file config/
done
