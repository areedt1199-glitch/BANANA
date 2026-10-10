from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Zone, AIPlantAssessment
from app.services.ai_phenotyping import AIPhenotypingService
from app.schemas.domain import AIPlantAssessmentResponse

router = APIRouter(prefix="/ai", tags=["AI Visual Phenotyping"])

@router.post("/assess-plant", response_model=AIPlantAssessmentResponse)
async def assess_banana_plant(
    zone_id: str = Form(...),
    known_planting_days: Optional[int] = Form(None),
    apply_stage_to_zone: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Mode 2: AI Visual Phenotyping Endpoint
    Accepts photo of Kluai Hom Thong plant (from LINE LIFF or Web Dashboard).
    Evaluates:
      - Growth Stage (Vegetative, Flowering/Bud, Fruit Bulking, Pre-Harvest)
      - Pseudostem girth, leaf count, fruit bunch emergence
      - Fruit angularity (เหลี่ยมผลกล้วยหอมทอง)
      - Disease risks (Fusarium wilt, Sigatoka leaf spots, K deficiency)
      - Generates custom prescription fertigation formula (N:P:K) & water ET0.
    """
    zone_res = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Run AI Vision Analysis
    ai_result = await AIPhenotypingService.analyze_plant_image(image_bytes, known_planting_days)

    assessment = AIPlantAssessment(
        id=str(uuid.uuid4()),
        tenant_id=zone.tenant_id,
        zone_id=zone.id,
        image_url=f"/uploads/banana_{uuid.uuid4().hex[:8]}.jpg", # Simulated/persisted image path
        predicted_growth_stage=ai_result["predicted_growth_stage"],
        confidence_score=ai_result["confidence_score"],
        estimated_age_days=ai_result.get("estimated_age_days"),
        pseudostem_girth_est_cm=ai_result.get("pseudostem_girth_est_cm"),
        active_leaves_count=ai_result.get("active_leaves_count"),
        bunch_detected=ai_result.get("bunch_detected", False),
        fruit_angularity_status=ai_result.get("fruit_angularity_status"),
        fusarium_risk_level=ai_result.get("fusarium_risk_level", "LOW"),
        sigatoka_leaf_spot_detected=ai_result.get("sigatoka_leaf_spot_detected", False),
        potassium_deficiency_detected=ai_result.get("potassium_deficiency_detected", False),
        recommended_et0_water_lpd=ai_result.get("recommended_et0_water_lpd"),
        recommended_fertilizer_formula=ai_result.get("recommended_fertilizer_formula"),
        ai_explanation_th=ai_result.get("ai_explanation_th"),
        created_at=datetime.now(timezone.utc)
    )
    db.add(assessment)

    if apply_stage_to_zone and zone.current_stage != assessment.predicted_growth_stage:
        zone.current_stage = assessment.predicted_growth_stage
        zone.stage_override_by_ai = True

    await db.commit()
    await db.refresh(assessment)

    return assessment
