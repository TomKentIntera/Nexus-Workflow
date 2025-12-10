from __future__ import annotations

from typing import Dict, List, Optional

import gradio as gr
import httpx
from fastapi import FastAPI
from gradio.routes import mount_gradio_app

from .config import get_settings

settings = get_settings()
app = FastAPI(title="Reviewer UI", version="0.1.0")


def _api_client() -> httpx.Client:
    return httpx.Client(base_url=settings.api_base_url, timeout=settings.request_timeout)


def _fetch_runs() -> List[Dict]:
    try:
        with _api_client() as client:
            response = client.get("/runs")
            response.raise_for_status()
            data = response.json()
            return data.get("runs", [])
    except httpx.HTTPError as exc:  # pragma: no cover - network issues
        print(f"[reviewer] failed to fetch runs: {exc}")
        return []


def _fetch_run(run_id: str) -> Optional[Dict]:
    try:
        with _api_client() as client:
            response = client.get(f"/runs/{run_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:  # pragma: no cover
        print(f"[reviewer] failed to fetch run {run_id}: {exc}")
        return None


def refresh_runs(current_value: Optional[str] = None) -> gr.Dropdown:
    runs = _fetch_runs()
    choices = [run["id"] for run in runs]
    selected = current_value if current_value in choices else (choices[0] if choices else None)
    return gr.Dropdown.update(choices=choices, value=selected)


def load_run_details(run_id: Optional[str]):
    if not run_id:
        return (
            "Select a run to view its images.",
            [],
            gr.CheckboxGroup.update(choices=[], value=[]),
            [],
            {},
        )

    run = _fetch_run(run_id)
    if not run:
        return (
            f"Run {run_id} not found.",
            [],
            gr.CheckboxGroup.update(choices=[], value=[]),
            [],
            {},
        )

    gallery_items = []
    checkbox_labels: List[str] = []
    lookup: Dict[str, str] = {}
    table_rows: List[List[str | int]] = []

    for image in sorted(run.get("images", []), key=lambda item: item.get("ordinal", 0)):
        caption = f"#{image['ordinal']} - {image['status']}"
        gallery_items.append([image.get("asset_uri"), caption])
        label = f"#{image['ordinal']} - {image['status'].upper()} ({image['id'][:8]})"
        checkbox_labels.append(label)
        lookup[label] = image["id"]
        table_rows.append(
            [
                image["id"],
                image.get("ordinal"),
                image.get("status"),
                image.get("asset_uri"),
            ]
        )

    status_md = (
        f"### Run {run['id']}\n"
        f"- **Status:** {run['status']}\n"
        f"- **Prompt:** {run['prompt']}\n"
        f"- **Images:** {len(run.get('images', []))}"
    )

    return (
        status_md,
        gallery_items,
        gr.CheckboxGroup.update(choices=checkbox_labels, value=[]),
        table_rows,
        lookup,
    )


def approve_selected(
    run_id: Optional[str],
    selections: Optional[List[str]],
    approved_by: Optional[str],
    notes: Optional[str],
    lookup: Dict[str, str],
) -> str:
    if not run_id:
        return "Please select a run before approving images."

    selections = selections or []
    if not selections:
        return "Select at least one image to approve."

    reviewer = (approved_by or settings.default_approver).strip()
    if not reviewer:
        return "Provide the reviewer name to continue."

    image_ids = [lookup.get(label) for label in selections]
    image_ids = [image_id for image_id in image_ids if image_id]
    if not image_ids:
        return "No matching images found for the current selection. Refresh the run and try again."

    successes = 0
    failures: List[str] = []
    with _api_client() as client:
        for image_id in image_ids:
            try:
                response = client.post(
                    f"/runs/{run_id}/images/{image_id}/approve",
                    json={"approved_by": reviewer, "notes": notes},
                )
                response.raise_for_status()
                successes += 1
            except httpx.HTTPError as exc:
                failures.append(f"{image_id[:8]}... ({exc})")

    message = f"Approved {successes} image(s)."
    if failures:
        message += " Failed: " + ", ".join(failures)
    return message


def build_interface() -> gr.Blocks:
    with gr.Blocks(title="Image Reviewer") as demo:
        gr.Markdown("# Image Reviewer\nMonitor workflow runs and approve generated images.")

        with gr.Row():
            run_dropdown = gr.Dropdown(label="Run", interactive=True)
            refresh_button = gr.Button("Refresh", variant="secondary")

        run_summary = gr.Markdown("Select a run to view its details.")
        gallery = gr.Gallery(label="Images", show_label=True, columns=5, height=400, value=[])
        image_table = gr.Dataframe(
            headers=["Image ID", "Ordinal", "Status", "Asset URI"],
            interactive=False,
            label="Image details",
            value=[],
        )

        selection_box = gr.CheckboxGroup(label="Images to approve", interactive=True)
        approver = gr.Textbox(label="Approved by", value=settings.default_approver)
        notes = gr.Textbox(label="Notes", lines=2, placeholder="Optional notes for webhook consumers")
        approve_button = gr.Button("Approve Selected", variant="primary")
        status_text = gr.Markdown()
        image_state = gr.State({})

        demo.load(refresh_runs, inputs=[run_dropdown], outputs=[run_dropdown])
        demo.load(load_run_details, inputs=[run_dropdown], outputs=[run_summary, gallery, selection_box, image_table, image_state])

        run_dropdown.change(
            load_run_details,
            inputs=[run_dropdown],
            outputs=[run_summary, gallery, selection_box, image_table, image_state],
        )

        refresh_button.click(refresh_runs, inputs=[run_dropdown], outputs=[run_dropdown]).then(
            load_run_details,
            inputs=[run_dropdown],
            outputs=[run_summary, gallery, selection_box, image_table, image_state],
        )

        approve_button.click(
            approve_selected,
            inputs=[run_dropdown, selection_box, approver, notes, image_state],
            outputs=[status_text],
        ).then(
            load_run_details,
            inputs=[run_dropdown],
            outputs=[run_summary, gallery, selection_box, image_table, image_state],
        )

    return demo


demo = build_interface()
app = mount_gradio_app(app, demo, path="/")


@app.get("/healthz", tags=["health"])
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}
