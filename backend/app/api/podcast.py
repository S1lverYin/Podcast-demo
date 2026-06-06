from fastapi import APIRouter, HTTPException, status

from app.schemas import PodcastRecommendationRead, PodcastRecommendationRequest
from app.services.podcast_recommendations import recommend_recent_podcasts


router = APIRouter()


@router.post("/recommendations", response_model=list[PodcastRecommendationRead])
def recommend_podcast_links(payload: PodcastRecommendationRequest) -> list[PodcastRecommendationRead]:
    """Recommend recent videos or podcasts similar to supplied links or keywords."""
    try:
        return recommend_recent_podcasts(
            payload.links,
            keywords=payload.keywords,
            max_results=payload.max_results,
            days=payload.days,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
