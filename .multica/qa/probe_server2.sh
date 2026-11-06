cd /d/codex/xiuxian/.multica/qa/probe2
export LAN_HOST=127.0.0.1 LAN_PORT=8899 ALLOW_LOCAL_AI=1 AI_REQUIRED=0 USE_CCSWITCH=0 LLM_API_KEY= NPC_TICK_INTERVAL=0 GAME_ENV=test
exec /d/codex/xiuxian/.venv/Scripts/python.exe -m server.app
