from fastapi import APIRouter, HTTPException, Response, status

from app.schemas import (
    PodcastCurationReportRead,
    PodcastCurationReportRequest,
    PodcastRecommendationRead,
    PodcastRecommendationRequest,
    PodcastSubscriptionCreate,
    PodcastSubscriptionRead,
)
from app.services.podcast_recommendations import (
    add_subscription_channel,
    delete_subscription_channel,
    generate_curation_report,
    list_subscription_channels,
    recommend_recent_podcasts,
)


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
            search_subscriptions=payload.search_subscriptions,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/subscriptions", response_model=list[PodcastSubscriptionRead])
def list_podcast_subscriptions() -> list[PodcastSubscriptionRead]:
    """Return locally configured podcast/video subscription channels."""
    return [
        PodcastSubscriptionRead(channel_id=item.channel_id, url=item.url, title=item.title)
        for item in list_subscription_channels()
    ]


@router.post("/subscriptions", response_model=PodcastSubscriptionRead, status_code=status.HTTP_201_CREATED)
def create_podcast_subscription(payload: PodcastSubscriptionCreate) -> PodcastSubscriptionRead:
    """Add a channel to the local subscription source list."""
    try:
        item = add_subscription_channel(payload.channel_id, payload.url, payload.title)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PodcastSubscriptionRead(channel_id=item.channel_id, url=item.url, title=item.title)


@router.delete("/subscriptions/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_podcast_subscription(channel_id: str) -> Response:
    """Delete a channel from the local subscription source list."""
    try:
        delete_subscription_channel(channel_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/curation-report", response_model=PodcastCurationReportRead)
def create_curation_report(payload: PodcastCurationReportRequest) -> PodcastCurationReportRead:
    """Generate a Chinese editorial curation report from recommendation results."""
    try:
        markdown = generate_curation_report(
            [item.model_dump() for item in payload.items],
            target_audience=payload.target_audience,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PodcastCurationReportRead(markdown=markdown)
