# Regenerate: vhs docs/assets/mt5-gateway-demo.tape
# (from the repo root; requires https://github.com/charmbracelet/vhs)
#
# Records the exact commands from the README quickstart and headless-login
# walkthrough. See docs/assets/demo-env.sh for what the recording stubs and why.

Output docs/assets/mt5-gateway-demo.gif

Set Shell bash
Set FontSize 18
Set Width 1200
Set Height 680
Set Theme "Dracula"
Set Padding 24
Set TypingSpeed 35ms

Hide
Type "source docs/assets/demo-env.sh && clear"
Enter
Show

Type "docker pull elitekaycy/mt5-gateway-api:latest"
Enter
Sleep 1500ms

Type "docker volume create mt5-gateway-config"
Enter
Sleep 800ms

Type "docker run -d --name mt5-gateway \"
Enter
Type "  --restart unless-stopped \"
Enter
Type "  -p 127.0.0.1:5001:5001 \"
Enter
Type "  -p 127.0.0.1:3000:3000 \"
Enter
Type "  -v mt5-gateway-config:/config \"
Enter
Type "  -e MT5_LOGIN=12345678 \"
Enter
Type "  -e MT5_PASSWORD='your-trading-password' \"
Enter
Type "  -e MT5_SERVER=Exness-MT5Trial9 \"
Enter
Type "  -e MT5_ENABLE_ALGO_TRADING=1 \"
Enter
Type "  -e API_KEY='change-this-long-random-token' \"
Enter
Type "  elitekaycy/mt5-gateway-api:latest"
Enter
Sleep 1200ms

Type "export API_KEY='change-this-long-random-token'"
Enter
Sleep 500ms

Type "curl http://localhost:5001/health/live"
Enter
Sleep 1200ms

Type `curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/health/ready`
Enter
Sleep 1800ms

Type `curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account`
Enter
Sleep 2500ms
