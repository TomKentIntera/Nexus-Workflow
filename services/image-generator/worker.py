"""
Worker that polls MySQL for QUEUED runs and processes them.
"""

import os
import time
import sys
import traceback
import json
from typing import Optional
from db import get_db_session, Run, RunImage, RunStatus, RunImageStatus
from generator import generate_images_for_run


def process_queued_runs():
    """Poll for QUEUED runs and process them."""
    poll_interval = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))  # seconds
    
    print("🚀 Image Generation Worker started")
    print(f"   Polling every {poll_interval} seconds")
    print(f"   Looking for runs with status: QUEUED")
    print()
    
    while True:
        try:
            with get_db_session() as session:
                # Find runs with QUEUED status
                queued_runs = session.query(Run).filter(
                    Run.status == RunStatus.QUEUED
                ).order_by(Run.created_at.asc()).limit(1).all()
                
                if queued_runs:
                    run = queued_runs[0]
                    print(f"📋 Found queued run: {run.id}")
                    print(f"   Prompt: {run.prompt[:100]}...")
                    
                    # Update status to GENERATING
                    run.status = RunStatus.GENERATING
                    session.commit()
                    
                    try:
                        # Parse parameters from parameter_blob (already JSON in database)
                        parameters = run.parameter_blob if run.parameter_blob else {}
                        
                        # Extract generation parameters
                        num_images = parameters.get("num_images", 1)
                        negative_prompt = parameters.get("negative_prompt", "blurry, low quality, distorted, watermark, text")
                        num_inference_steps = parameters.get("steps", 28)
                        guidance_scale = parameters.get("guidance", 7.5)
                        width = parameters.get("width", 1024)
                        height = parameters.get("height", 1024)
                        seed = parameters.get("seed")
                        saturation = parameters.get("saturation", 1.2)
                        contrast = parameters.get("contrast", 1.1)
                        model_id = parameters.get("model_id", "Heartsync/NSFW-Uncensored")
                        
                        print(f"   Generating {num_images} image(s)...")
                        
                        # Generate images
                        generate_images_for_run(
                            run_id=run.id,
                            prompt=run.prompt,
                            num_images=num_images,
                            negative_prompt=negative_prompt,
                            num_inference_steps=num_inference_steps,
                            guidance_scale=guidance_scale,
                            width=width,
                            height=height,
                            seed=seed,
                            saturation_boost=saturation,
                            contrast_boost=contrast,
                            model_id=model_id,
                            session=session
                        )
                        
                        # Update status to READY
                        run.status = RunStatus.READY
                        session.commit()
                        
                        print(f"✅ Run {run.id} completed successfully")
                        print()
                        
                    except Exception as e:
                        print(f"❌ Error processing run {run.id}: {str(e)}")
                        traceback.print_exc()
                        
                        # Update status to ERROR
                        run.status = RunStatus.ERROR
                        session.commit()
                        print()
                else:
                    # No queued runs, wait before next poll
                    time.sleep(poll_interval)
                    
        except Exception as e:
            print(f"❌ Error in worker loop: {str(e)}")
            traceback.print_exc()
            time.sleep(poll_interval)


if __name__ == "__main__":
    import os
    try:
        process_queued_runs()
    except KeyboardInterrupt:
        print("\n👋 Worker stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

