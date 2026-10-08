from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "api_key_loaded": request.app.state.llm is not None,
        "model": request.app.state.config.openai_model,
        "git_available": request.app.state.git_available,
    }
