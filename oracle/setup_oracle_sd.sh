#!/usr/bin/env bash
# Setup Stable Diffusion (AUTOMATIC1111) di Oracle A1 Always Free (ARM 24GB)
# Jalankan: bash setup_oracle_sd.sh
set -e
echo "═══ [1/5] Update sistem ═══"
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y python3-venv git libgl1 libglib2.0-0 aria2

echo "═══ [2/5] Clone SD WebUI ═══"
cd ~
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git 2>/dev/null || true
cd stable-diffusion-webui

echo "═══ [3/5] Model (SD 1.5, ~4GB) ═══"
mkdir -p models/Stable-diffusion
if [ ! -f models/Stable-diffusion/sd-v1-5.safetensors ]; then
  aria2c --console-log-level=error -c -x 16 -s 16 -k 1M \
    -d models/Stable-diffusion -o sd-v1-5.safetensors \
    "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned.safetensors" \
  || echo "⚠️ download model gagal — ulang nanti"
fi

echo "═══ [4/5] API mode (port 7861) ═══"
# --api = REST API buat di-wire ke bot; --skip-torch-cuda-test karena ARM/CPU
cat > run_api.sh <<'EOF'
#!/usr/bin/env bash
cd ~/stable-diffusion-webui
./webui.sh --api --listen --port 7861 --skip-torch-cuda-test --precision full --no-half
EOF
chmod +x run_api.sh

echo "═══ [5/5] Systemd service ═══"
sudo tee /etc/systemd/system/sdwebui.service > /dev/null <<EOF
[Unit]
Description=Stable Diffusion WebUI (API)
After=network.target
[Service]
User=$USER
ExecStart=/home/$USER/stable-diffusion-webui/run_api.sh
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now sdwebui
echo "✅ SELESAI — cek: curl http://localhost:7861/sdapi/v1/sd-models"
echo "   Butuh ~3-5 menit pertama buat warm-up (unduh torch dll)."
