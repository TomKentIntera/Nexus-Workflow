"""
HTTP API for image generation.
Provides REST endpoints for generating images using the Heartsync model.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from generator import generate_images

app = FastAPI(title="Image Generator API", version="1.0.0")


class GenerateRequest(BaseModel):
    tags: str
    run_id: str
    num_images: int = 1
    webhook_url: str
    output_dir: Optional[str] = None
    negative_prompt: Optional[str] = None
    steps: Optional[int] = None
    guidance: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    saturation: Optional[float] = None
    contrast: Optional[float] = None
    model_id: Optional[str] = None


class GenerateResponse(BaseModel):
    success: bool
    message: str
    run_id: str
    task_id: Optional[str] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "image-generator"}


@app.post("/generate", response_model=GenerateResponse)
async def generate_images_endpoint(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Generate images based on the provided parameters.
    This endpoint starts the generation process in the background.
    """
    try:
        # Prepare parameters
        output_dir = request.output_dir or "/app/generated-images"
        
        # Run in background
        task_id = f"task_{int(datetime.now().timestamp() * 1000)}"
        background_tasks.add_task(
            run_generation_task,
            prompt=request.tags,
            run_id=request.run_id,
            num_images=request.num_images,
            webhook_url=request.webhook_url,
            output_dir=output_dir,
            negative_prompt=request.negative_prompt,
            num_inference_steps=request.steps,
            guidance_scale=request.guidance,
            width=request.width,
            height=request.height,
            seed=request.seed,
            saturation_boost=request.saturation,
            contrast_boost=request.contrast,
            model_id=request.model_id,
            task_id=task_id
        )
        
        return GenerateResponse(
            success=True,
            message=f"Image generation started for run_id: {request.run_id}",
            run_id=request.run_id,
            task_id=task_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting generation: {str(e)}")


def run_generation_task(
    prompt: str,
    run_id: str,
    num_images: int,
    webhook_url: str,
    output_dir: str,
    task_id: str,
    negative_prompt: Optional[str] = None,
    num_inference_steps: Optional[int] = None,
    guidance_scale: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    seed: Optional[int] = None,
    saturation_boost: Optional[float] = None,
    contrast_boost: Optional[float] = None,
    model_id: Optional[str] = None
):
    """Run the generation task in the background."""
    try:
        print(f"Starting generation task {task_id} for run_id: {run_id}")
        
        result = generate_images(
            prompt=prompt,
            run_id=run_id,
            num_images=num_images,
            webhook_url=webhook_url,
            output_dir=output_dir,
            negative_prompt=negative_prompt or "blurry, low quality, distorted, watermark, text",
            num_inference_steps=num_inference_steps or 28,
            guidance_scale=guidance_scale or 7.5,
            width=width or 1024,
            height=height or 1024,
            seed=seed,
            saturation_boost=saturation_boost or 1.2,
            contrast_boost=contrast_boost or 1.1,
            model_id=model_id or "Heartsync/NSFW-Uncensored"
        )
        
        print(f"Generation task {task_id} completed successfully")
        print(f"Generated {result['success_count']}/{result['requested_count']} images")
            
    except Exception as e:
        print(f"Exception in generation task {task_id}: {str(e)}")
        import traceback
        traceback.print_exc()


@app.get("/status")
async def get_status():
    """Get service status."""
    return {
        "status": "running",
        "service": "image-generator",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

