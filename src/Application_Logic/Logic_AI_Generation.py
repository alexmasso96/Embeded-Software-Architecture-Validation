"""
AI Test Case Generation — generation job (pure logic).

Phase 0 (pywebview migration): Qt-free. The Qt tab controller lives in
UI/tab_ai_generation.py and runs `run_generation_job` on a worker thread;
after Phase 1 the FastAPI job manager runs it as the `generate_tests` job.
The heavy lifting (context building, provider calls, output writing) already
lives in Logic_AI_Context / Logic_AI_Providers.
"""
from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Context as ctx

# DB meta keys for non-secret preferences (secrets live in the credential store).
_META_PROVIDER = "ai_sel_provider"
_META_MODEL = "ai_sel_model"
_META_SOURCE = "ai_source_path"


def run_generation_job(provider_id, model, rules, prompt, source_path,
                       output_dir, model_name, hlt_title, test_cases,
                       progress_cb=lambda msg: None,
                       case_done_cb=lambda tc_id, text: None,
                       stop_check=lambda: False):
    """Generates low-level test designs for the selected cases and writes
    <Model>_LowLevel.md. Run me on a worker thread.

    Callbacks: ``progress_cb(msg)`` narrates phases, ``case_done_cb(tc_id,
    text)`` fires per generated case (the UI live-renders), ``stop_check()``
    returning True aborts via ``providers.AIStopped``.

    Returns the output file path; raises on failure (including AIStopped).
    """
    progress_cb("Analyzing source code for relevant context…")
    combined = "\n".join(tc["raw"] for tc in test_cases)
    source_ctx = ctx.build_source_context(source_path, [combined]) if source_path else ""
    if source_ctx:
        progress_cb(f"Source context: {len(source_ctx)} chars.")
    else:
        progress_cb("No source context (path empty or no match).")

    generated = {}
    for i, tc in enumerate(test_cases, 1):
        if stop_check():
            raise providers.AIStopped("Stopped by user.")
        progress_cb(f"[{i}/{len(test_cases)}] Generating: {tc['title']}")
        messages = ctx.build_messages(rules, prompt, tc["raw"], source_ctx)
        text = providers.generate(
            provider_id, model, messages,
            stream_cb=None, stop_check=stop_check,
        )
        generated[tc["id"]] = text
        case_done_cb(tc["id"], text)

    return ctx.write_lowlevel_output(
        output_dir, model_name, hlt_title, test_cases, generated)
