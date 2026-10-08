import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

# ---------------------------------------------------------------------------
# /agent is expected to be a PERSISTENT storage bucket (mounted with write
# permission) — e.g. on Hugging Face Spaces, attach your Persistent Storage
# volume at this exact path. Everything any agent needs to remember
# (sqlite state, thread index, uploaded files) is written ONLY under here,
# so it survives Space restarts/redeploys instead of living on the
# ephemeral container filesystem.
#
# NOTE: many "persistent storage" buckets (including S3-backed / object
# storage mounts) behave like S3, not like a normal local disk: no real
# file locking, no shared-memory mmap, sometimes only whole-object
# read/write. SQLite's default WAL journal mode depends on mmap + proper
# file locks and can hang or quietly corrupt on that kind of storage — so
# every checkpointer created here is forced into the plain rollback
# journal instead (see open_agent_sqlite below).
# ---------------------------------------------------------------------------
AGENT_ROOT = "/agent"


def agent_dir(agent_name: str) -> str:
    """
    Returns (and creates if needed) /agent/<agent_name>/, and fails loudly
    with a clear message if that location isn't actually writable — instead
    of silently falling back to ephemeral local storage.

    The write-check itself is written to be tolerant of S3-style / object
    storage buckets: it only requires that a file can be CREATED there.
    Deleting it afterwards is best-effort only, since some object-storage
    gateways don't support an immediate delete-after-create and that alone
    doesn't mean the bucket isn't writable — treating it as fatal caused a
    false-positive crash on exactly that kind of storage.
    """
    path = os.path.join(AGENT_ROOT, agent_name)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(
            f"'{path}' ফোল্ডার তৈরি করা যায়নি। '/agent' একটি persistent storage "
            f"বাকেট (যেমন HF Space-এর Persistent Storage) হিসেবে সঠিক পাথে "
            f"মাউন্ট করা আছে কিনা যাচাই করুন. (আসল এরর: {exc})"
        ) from exc

    probe = os.path.join(path, "write_test.tmp")
    try:
        with open(probe, "w") as f:
            f.write("ok")
    except Exception as exc:
        raise RuntimeError(
            f"'{path}' পাথে write access পাওয়া যায়নি। এই অ্যাপের সব agent-এর "
            f"memory/state '/agent' নামের একটি persistent storage বাকেটে রাখা হয় — "
            f"HF Space-এ Persistent Storage সেই '/agent' পাথে সঠিকভাবে মাউন্ট করা "
            f"আছে কিনা এবং তাতে write permission আছে কিনা যাচাই করুন. "
            f"(আসল এরর: {exc})"
        ) from exc

    try:
        os.remove(probe)
    except Exception:
        pass  # best-effort cleanup only, see docstring above

    return path


def open_agent_sqlite(db_path: str) -> SqliteSaver:
    """
    Opens (creating if needed) a sqlite-backed LangGraph checkpointer at
    db_path, configured to be safe on S3-style / network object storage:
    plain rollback journal instead of WAL (no mmap / shared-memory
    dependency) and full fsync-on-commit durability.
    """
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=FULL;")
        saver = SqliteSaver(conn)
        saver.setup()
        return saver
    except Exception as exc:
        raise RuntimeError(
            f"'{db_path}'-এ sqlite মেমরি ফাইল খোলা/সেটআপ করা যায়নি। যদি '/agent' "
            f"একটি S3-স্টাইল object storage বাকেট হয়, নিশ্চিত করুন সেটি সাধারণ "
            f"ফাইল read/write/delete সাপোর্ট করে (শুধু whole-object PUT নয়)। "
            f"(আসল এরর: {exc})"
        ) from exc
