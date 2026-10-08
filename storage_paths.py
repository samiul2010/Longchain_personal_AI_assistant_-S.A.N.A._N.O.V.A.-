import os

# ---------------------------------------------------------------------------
# /agent is expected to be a PERSISTENT storage bucket (mounted with write
# permission) — e.g. on Hugging Face Spaces, attach your Persistent Storage
# volume at this exact path. Everything any agent needs to remember
# (sqlite state, thread index, uploaded files) is written ONLY under here,
# so it survives Space restarts/redeploys instead of living on the
# ephemeral container filesystem.
# ---------------------------------------------------------------------------
AGENT_ROOT = "/agent"


def agent_dir(agent_name: str) -> str:
    """
    Returns (and creates if needed) /agent/<agent_name>/, and fails loudly
    with a clear message if that location isn't actually writable — instead
    of silently falling back to ephemeral local storage.
    """
    path = os.path.join(AGENT_ROOT, agent_name)
    os.makedirs(path, exist_ok=True)

    probe = os.path.join(path, ".write_test")
    try:
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as exc:
        raise RuntimeError(
            f"'{path}' পাথে write access পাওয়া যায়নি। এই অ্যাপের সব agent-এর "
            f"memory/state '/agent' নামের একটি persistent storage বাকেটে রাখা হয় — "
            f"HF Space-এ Persistent Storage সেই '/agent' পাথে সঠিকভাবে মাউন্ট করা "
            f"আছে কিনা এবং তাতে write permission আছে কিনা যাচাই করুন. "
            f"(আসল এরর: {exc})"
        ) from exc

    return path
