import gradio as gr

from agents import main_agent


def chat_fn(message, history):
    """
    Gradio multimodal ChatInterface callback.

    `message` is a dict: {"text": str, "files": [local_path, ...]}
    when multimodal=True. We forward the text and (at most) the first
    attached file straight into main_agent(user_command=, user_attachment=).
    """
    text = message.get("text", "") if isinstance(message, dict) else str(message)
    files = message.get("files", []) if isinstance(message, dict) else []
    attachment = files[0] if files else None
    import mcp_diagnostic
    agent_instance = _vs_ide_sub_agent()
    logger.info(f"[MCP-DIAG] Agent tools count: {len(agent_instance.tools or [])}")
    logger.info(f"[MCP-DIAG] Agent tool names: {[t.name for t in (agent_instance.tools or [])]}")

    return main_agent(user_command=text, user_attachment=attachment)


demo = gr.ChatInterface(
    fn=chat_fn,
    multimodal=True,
    title="Personal Assistant",
    description="Chat with your assistant. You can attach a file with your message.",
)
import mcp_diagnostic

chat_agent=demo.launch(server_name="0.0.0.0", server_port=7860)
