from fastapi import APIRouter, Depends

from src.application.answer.answer_query import AnswerQuery
from src.domain.entities import Query
from src.interfaces.dependencies.answer import get_answer_query
from src.interfaces.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def answer_query(
    body: QueryRequest,
    use_case: AnswerQuery = Depends(get_answer_query),
) -> QueryResponse:
    answer = await use_case.execute(Query(text=body.question))
    return QueryResponse(answer=answer.text)
