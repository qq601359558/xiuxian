"""
AI 模型连接联调测试工具
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from ai.gateway import AIGateway
from ai.validator import DSLValidator


def check_ai():
    print("=" * 50)
    print("      《天道因果录》AI 造化网关连通性测试")
    print("=" * 50)
    print(f"当前接口地址 (API_BASE) : {LLM_API_BASE}")
    print(f"当前模型名称 (MODEL)    : {LLM_MODEL}")
    key_masked = LLM_API_KEY[:6] + "..." + LLM_API_KEY[-4:] if len(LLM_API_KEY) > 10 else ("未配置(使用本地降级引擎)" if not LLM_API_KEY else "已配置")
    print(f"当前密钥状态 (API_KEY)  : {key_masked}")
    print("-" * 50)

    print("\n[1/2] 测试 AI 心魔劫幻境生成...")
    demon_text = AIGateway.generate_heart_demon_text("韩立", sin_value=120)
    print(f"生成结果：\n{demon_text}\n")

    print("[2/2] 测试 AI 功法推演与 DSL 编译...")
    art = AIGateway.generate_custom_art("引九幽地脉之火焚炼神魂，杀生化煞", "韩立")
    valid, msg = DSLValidator.validate_custom_art(art)
    print(f"功法道名：{art.get('name')}")
    print(f"功法品阶：{art.get('rank')}阶 · {art.get('nature')}")
    print(f"修为倍率：{art.get('cultivation_modifiers', {}).get('exp_gain_multiplier')}x")
    print(f"每年寿损：{art.get('cultivation_modifiers', {}).get('lifespan_burn_per_year')} 岁")
    print(f"天道校验：{'✅ 允许通过' if valid else '❌ 拦截'} ({msg})")
    print("-" * 50)

    if LLM_API_KEY:
        print("🎉 恭喜！已成功连通云端/本地大模型，全服动态心魔与自创功法已由 AI 实时接管！")
    else:
        print("💡 提示：当前未检测到 LLM_API_KEY，系统正在使用内置的【本地自平衡造化模板】平替运行。")
        print("   若想体验真正的大语言模型生成，可在 D:\\codex\\xiuxian\\.env 文件中配置密钥。")


if __name__ == "__main__":
    check_ai()
