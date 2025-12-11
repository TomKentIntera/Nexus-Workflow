"""
Image generation module for Heartsync model.
Provides API functions for generating images with MinIO storage integration.
"""

from __future__ import annotations

import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import os
from typing import Optional, Dict, Tuple
from datetime import datetime
import json
from io import BytesIO
from minio import Minio
from minio.error import S3Error
from sqlalchemy.orm import Session
from db import RunImage, RunImageStatus

# Set Hugging Face cache directory
os.environ["HF_HOME"] = os.path.join(os.getcwd(), "hf_cache")
os.environ["HF_HUB_CACHE"] = os.path.join(os.getcwd(), "hf_cache")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(os.getcwd(), "hf_cache")


class HeartsyncModel:
    def __init__(self, model_id: str = "Heartsync/NSFW-Uncensored"):
        """Initialize the Heartsync NSFW-Uncensored model."""
        self.model_id = model_id
        self.pipe = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.loaded = False
        
        print(f"Using device: {self.device}")
        
    def load_model(self):
        """Load the model."""
        try:
            print("🔄 Loading model... This may take a few minutes on first run.")
            print("📥 Downloading model components (this only happens once)...")
            
            # Load the pipeline with explicit cache directory
            cache_dir = os.path.join(os.getcwd(), "hf_cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            print("⬇️  Downloading model files... (this may take 5-15 minutes)")
            
            # Enable verbose logging for Hugging Face downloads
            import logging
            logging.getLogger("transformers").setLevel(logging.INFO)
            
            self.pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                use_safetensors=True,
                variant="fp16" if self.device == "cuda" else None,
                cache_dir=cache_dir,
                resume_download=True
            )
            
            print("🖥️  Moving model to device...")
            self.pipe = self.pipe.to(self.device)
            
            print("⚡ Enabling memory efficient attention...")
            if self.device == "cuda":
                self.pipe.enable_model_cpu_offload()
            # For CPU mode, the model is already on CPU, no offload needed
            
            print("✅ Model loaded successfully!")
            print("🚀 Ready to generate images!")
            
            self.loaded = True
            return True
            
        except Exception as e:
            error_msg = f"❌ Error loading model: {str(e)}"
            print(error_msg)
            raise
    
    def generate_image(
        self, 
        prompt: str, 
        negative_prompt: str = "",
        num_inference_steps: int = 28,
        guidance_scale: float = 7.5,
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        saturation_boost: float = 1.2,
        contrast_boost: float = 1.1
    ) -> Tuple[Image.Image, int]:
        """Generate a single image based on the prompt."""
        if not self.loaded or self.pipe is None:
            raise RuntimeError("Model is not loaded. Please load the model first.")
        
        try:
            # Handle seed: if 0 or None, generate a random seed
            if seed is None or seed == 0:
                actual_seed = torch.randint(0, 2**32 - 1, (1,)).item()
            else:
                actual_seed = seed
            
            # Set the seed for reproducible generation
            torch.manual_seed(actual_seed)
            if self.device == "cuda":
                torch.cuda.manual_seed(actual_seed)
            
            # Generate image
            generator = torch.Generator(device=self.device).manual_seed(actual_seed)
            
            if self.device == "cuda":
                with torch.autocast(self.device):
                    result = self.pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        num_images_per_prompt=1,
                        generator=generator,
                    )
                    image = result.images[0]
            else:
                # CPU mode
                result = self.pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    width=width,
                    height=height,
                    num_images_per_prompt=1,
                    generator=generator,
                )
                image = result.images[0]
            
            # Enhance colors and contrast
            image = self.enhance_image_colors(image, saturation_boost, contrast_boost)
            
            return image, actual_seed
            
        except Exception as e:
            raise RuntimeError(f"Error generating image: {str(e)}")
    
    def enhance_image_colors(self, image: Image.Image, saturation_boost: float = 1.2, contrast_boost: float = 1.1) -> Image.Image:
        """Enhance image colors and contrast."""
        from PIL import ImageEnhance
        import numpy as np
        
        # Apply color enhancement
        # 1. Increase saturation
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance(saturation_boost)
        
        # 2. Increase contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(contrast_boost)
        
        # 3. Increase brightness slightly
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.05)
        
        # 4. Apply gamma correction for better color distribution
        img_array = np.array(image)
        img_array = np.power(img_array / 255.0, 0.95) * 255.0
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        
        return Image.fromarray(img_array)
    
    def save_image_with_metadata(
        self, 
        image: Image.Image, 
        prompt: str, 
        negative_prompt: str,
        num_inference_steps: int,
        guidance_scale: float,
        width: int,
        height: int,
        seed: int,
        saturation_boost: float,
        contrast_boost: float,
        run_id: str,
        output_dir: str,
        minio_client: Optional[Minio] = None,
        minio_bucket: Optional[str] = None,
        minio_public_base: Optional[str] = None
    ) -> Dict[str, str]:
        """Save image and metadata to organized folders and optionally upload to MinIO.
        
        Returns:
            Dict with 'local_path' and optionally 'minio_uri' keys.
        """
        # Create directory structure: {output_dir}/{run_id}/
        save_dir = os.path.join(output_dir, run_id)
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate timestamp in seconds
        timestamp = int(datetime.now().timestamp())
        
        # Save image locally
        image_path = os.path.join(save_dir, f"{timestamp}.png")
        image.save(image_path)
        
        # Prepare image bytes for MinIO upload
        image_bytes = BytesIO()
        image.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        image_data = image_bytes.read()
        
        # Create metadata
        metadata = {
            "timestamp": timestamp,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "width": width,
            "height": height,
            "saturation_boost": saturation_boost,
            "contrast_boost": contrast_boost,
            "model_id": self.model_id,
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(),
            "image_path": image_path
        }
        
        # Save metadata as JSON file
        metadata_path_json = os.path.join(save_dir, f"{timestamp}.json")
        with open(metadata_path_json, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        result = {"local_path": image_path}
        
        # Upload to MinIO if configured
        if minio_client and minio_bucket:
            try:
                # Object name should not include bucket name (bucket is already "runs")
                object_name = f"{run_id}/{timestamp}.png"
                
                # Ensure bucket exists
                if not minio_client.bucket_exists(minio_bucket):
                    minio_client.make_bucket(minio_bucket)
                    print(f"✅ Created MinIO bucket: {minio_bucket}")
                
                # Upload image
                minio_client.put_object(
                    minio_bucket,
                    object_name,
                    BytesIO(image_data),
                    length=len(image_data),
                    content_type="image/png"
                )
                
                # Determine MinIO URI
                if minio_public_base:
                    minio_uri = f"{minio_public_base.rstrip('/')}/{object_name}"
                else:
                    minio_uri = f"s3://{minio_bucket}/{object_name}"
                
                result["minio_uri"] = minio_uri
                metadata["minio_uri"] = minio_uri
                
                # Update metadata file with MinIO URI
                with open(metadata_path_json, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Image uploaded to MinIO: {minio_uri}")
                
            except S3Error as e:
                print(f"⚠️  Warning: Failed to upload to MinIO: {str(e)}")
            except Exception as e:
                print(f"⚠️  Warning: Error uploading to MinIO: {str(e)}")
        
        return result


def get_minio_client() -> Optional[Minio]:
    """Create and return MinIO client from environment variables."""
    minio_endpoint = os.environ.get("MINIO_ENDPOINT")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")
    
    if not (minio_endpoint and minio_access_key and minio_secret_key):
        return None
    
    try:
        # Remove protocol from endpoint if present
        endpoint = minio_endpoint.replace("http://", "").replace("https://", "")
        secure = minio_endpoint.startswith("https://")
        
        client = Minio(
            endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=secure
        )
        return client
    except Exception as e:
        print(f"⚠️  Warning: Failed to create MinIO client: {str(e)}")
        return None


def save_run_image_to_db(
    session: Session,
    run_id: str,
    ordinal: int,
    asset_uri: str,
    thumb_uri: Optional[str] = None,
    notes: Optional[str] = None
) -> RunImage:
    """Save a RunImage record to the database."""
    run_image = RunImage(
        run_id=run_id,
        ordinal=ordinal,
        asset_uri=asset_uri,
        thumb_uri=thumb_uri,
        status=RunImageStatus.GENERATED,
        notes=notes
    )
    session.add(run_image)
    session.flush()  # Flush to get the ID
    return run_image


def generate_images_for_run(
    run_id: str,
    prompt: str,
    num_images: int = 1,
    output_dir: str = "./generated-images",
    negative_prompt: str = "blurry, low quality, distorted, watermark, text",
    num_inference_steps: int = 28,
    guidance_scale: float = 7.5,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    saturation_boost: float = 1.2,
    contrast_boost: float = 1.1,
    model_id: str = "Heartsync/NSFW-Uncensored",
    session: Optional[Session] = None
):
    """
    Generate images for a run and save RunImage records to the database.
    
    Args:
        session: Database session (required for writing to DB)
    """
    from db import get_db_session
    
    # Use provided session or create a new one
    if session is None:
        with get_db_session() as db_session:
            return generate_images_for_run(
                run_id=run_id,
                prompt=prompt,
                num_images=num_images,
                output_dir=output_dir,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                seed=seed,
                saturation_boost=saturation_boost,
                contrast_boost=contrast_boost,
                model_id=model_id,
                session=db_session
            )
    
    prompt = prompt.strip()
    
    print(f"🎨 Starting image generation")
    print(f"   Run ID: {run_id}")
    print(f"   Prompt: {prompt}")
    print(f"   Number of images: {num_images}")
    print()
    
    # Initialize MinIO client if configured
    minio_client = get_minio_client()
    minio_bucket = os.environ.get("MINIO_BUCKET", "runs")
    minio_public_base = os.environ.get("MINIO_PUBLIC_BASE")
    
    if minio_client:
        print(f"✅ MinIO client initialized (bucket: {minio_bucket})")
    else:
        print("ℹ️  MinIO upload disabled (using local storage only)")
    print()
    
    # Initialize model
    print("Initializing model...")
    model = HeartsyncModel(model_id=model_id)
    
    # Load model
    print("Loading model (this may take a while on first run)...")
    model.load_model()
    print()
    
    # Generate images
    base_seed = seed if seed is not None else None
    
    for i in range(num_images):
        print(f"Generating image {i+1}/{num_images}...")
        
        # Use different seed for each image if base seed is provided
        current_seed = base_seed + i if base_seed is not None else None
        
        try:
            # Generate image
            image, actual_seed = model.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                seed=current_seed,
                saturation_boost=saturation_boost,
                contrast_boost=contrast_boost
            )
            
            # Save image with metadata and upload to MinIO if configured
            save_result = model.save_image_with_metadata(
                image=image,
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                seed=actual_seed,
                saturation_boost=saturation_boost,
                contrast_boost=contrast_boost,
                run_id=run_id,
                output_dir=output_dir,
                minio_client=minio_client,
                minio_bucket=minio_bucket if minio_client else None,
                minio_public_base=minio_public_base
            )
            
            image_path = save_result["local_path"]
            minio_uri = save_result.get("minio_uri")
            
            # Use MinIO URI if available, otherwise use local path
            asset_uri = minio_uri if minio_uri else image_path
            
            # Save to database
            run_image = save_run_image_to_db(
                session=session,
                run_id=run_id,
                ordinal=i + 1,  # 1-indexed
                asset_uri=asset_uri,
                thumb_uri=None,  # Could generate thumbnail later
                notes=None
            )
            
            print(f"✅ Image {i+1} saved: {image_path}")
            if minio_uri:
                print(f"   MinIO URI: {minio_uri}")
            print(f"   Database record created: {run_image.id}")
            print()
            
        except Exception as e:
            print(f"❌ Error generating image {i+1}: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"🎉 Generation complete!")
    print(f"   Run ID: {run_id}")
    print()


def generate_images(
    prompt: str,
    run_id: str,
    num_images: int = 1,
    webhook_url: str = "",
    output_dir: str = "./generated-images",
    negative_prompt: str = "blurry, low quality, distorted, watermark, text",
    num_inference_steps: int = 28,
    guidance_scale: float = 7.5,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    saturation_boost: float = 1.2,
    contrast_boost: float = 1.1,
    model_id: str = "Heartsync/NSFW-Uncensored"
) -> Dict[str, any]:
    """
    Generate images using the Heartsync model.
    
    Returns:
        Dict with 'generated_paths' (list of local paths) and 'results' (list of result dicts)
    """
    prompt = prompt.strip()
    
    print(f"🎨 Starting image generation")
    print(f"   Run ID: {run_id}")
    print(f"   Prompt: {prompt}")
    print(f"   Number of images: {num_images}")
    print(f"   Output directory: {output_dir}/{run_id}")
    print()
    
    # Initialize MinIO client if configured
    minio_client = get_minio_client()
    minio_bucket = os.environ.get("MINIO_BUCKET", "runs")
    minio_public_base = os.environ.get("MINIO_PUBLIC_BASE")
    
    if minio_client:
        print(f"✅ MinIO client initialized (bucket: {minio_bucket})")
    else:
        print("ℹ️  MinIO upload disabled (using local storage only)")
    print()
    
    # Initialize model
    print("Initializing model...")
    model = HeartsyncModel(model_id=model_id)
    
    # Load model
    print("Loading model (this may take a while on first run)...")
    model.load_model()
    print()
    
    # Generate images
    generated_paths = []
    results = []
    base_seed = seed if seed is not None else None
    
    for i in range(num_images):
        print(f"Generating image {i+1}/{num_images}...")
        
        # Use different seed for each image if base seed is provided
        current_seed = base_seed + i if base_seed is not None else None
        
        try:
            # Generate image
            image, actual_seed = model.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                seed=current_seed,
                saturation_boost=saturation_boost,
                contrast_boost=contrast_boost
            )
            
            # Save image with metadata and upload to MinIO if configured
            save_result = model.save_image_with_metadata(
                image=image,
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                seed=actual_seed,
                saturation_boost=saturation_boost,
                contrast_boost=contrast_boost,
                run_id=run_id,
                output_dir=output_dir,
                minio_client=minio_client,
                minio_bucket=minio_bucket if minio_client else None,
                minio_public_base=minio_public_base
            )
            
            image_path = save_result["local_path"]
            minio_uri = save_result.get("minio_uri")
            
            generated_paths.append(image_path)
            result_item = {
                "local_path": image_path,
                "minio_uri": minio_uri,
                "seed": actual_seed
            }
            results.append(result_item)
            
            print(f"✅ Image {i+1} saved: {image_path}")
            if minio_uri:
                print(f"   MinIO URI: {minio_uri}")
            
            # Post webhook if URL provided
            if webhook_url:
                post_webhook(webhook_url, image_path, run_id, prompt, minio_uri)
            print()
            
        except Exception as e:
            print(f"❌ Error generating image {i+1}: {str(e)}")
            continue
    
    print(f"🎉 Generation complete!")
    print(f"   Generated {len(generated_paths)}/{num_images} images")
    print(f"   All images saved to: {os.path.join(output_dir, run_id)}")
    
    if len(generated_paths) < num_images:
        print(f"⚠️  Warning: Only {len(generated_paths)} out of {num_images} images were generated successfully")
    
    return {
        "generated_paths": generated_paths,
        "results": results,
        "success_count": len(generated_paths),
        "requested_count": num_images
    }

