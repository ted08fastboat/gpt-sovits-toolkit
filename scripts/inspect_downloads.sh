#!/bin/bash
# 盘点 ~/Downloads 里的 GPT-SoVITS 权重文件（需要提权：Downloads 受沙箱/TCC 保护）
set -u
echo "===== ~/Downloads 列表 ====="
ls -la "$HOME/Downloads" 2>&1 | head -60

echo
echo "===== 权重类文件 ====="
find "$HOME/Downloads" -maxdepth 3 -type f \( -name "*.ckpt" -o -name "*.pth" -o -name "*.pt" \) -print0 2>/dev/null |
while IFS= read -r -d '' f; do
  size=$(stat -f %z "$f")
  head2=$(xxd -p -l 2 "$f")
  printf '%s\n  大小: %s 字节 (%.1f MB)  头部: %s\n' "$f" "$size" "$(echo "scale=1; $size/1048576" | bc)" "$head2"
done

echo
echo "===== 目录内非权重文件（前 20 个） ====="
ls "$HOME/Downloads" 2>/dev/null | head -20

echo
echo "===== 桌面快捷方式 ====="
mkdir -p "$HOME/Desktop" 2>&1
cat > "$HOME/Desktop/GPT-SoVITS WebUI.command" <<'EOF'
#!/bin/bash
# 双击即可启动 GPT-SoVITS WebUI
exec "$HOME/GPT-SoVITS/start-webui.sh"
EOF
chmod 755 "$HOME/Desktop/GPT-SoVITS WebUI.command"
ls -l "$HOME/Desktop/GPT-SoVITS WebUI.command" 2>&1
echo "DESKTOP-DONE"
