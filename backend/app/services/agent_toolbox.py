"""The read-only tool surface the judgment agents see.

From the Agentic Workflow doc: the criteria, verifier and mediator agents
get `read_deal`, `read_criteria` and `read_deliverable`, all read-only, and
"no agent holds an open-ended 'pay' capability".

Routing agent context through this one narrow class is what makes that
checkable instead of aspirational:

  * it exposes three reads and nothing else — there is no method here that
    writes, settles, pays, refunds or transitions anything, and a test
    asserts that by inspection;
  * each read returns a purpose-built value object carrying only the fields
    the agent needs, so the model never sees emails, PayPal ids, account
    references or password hashes even by accident. That is the SRS privacy
    requirement — "only the data needed to verify a deliverable is sent to
    the model" — enforced at the boundary rather than remembered at each
    call site;
  * every toolbox is scoped to a single deal id at construction, so an
    agent reasoning about one deal cannot read another.
"""

from __future__ import annotations

import uuid

from app.domain.errors import DealNotFound
from app.integrations.ai.interface import DealContext, DeliverableContext
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository

# Names the agents' tools are documented under, used in logs and in the
# write-up. Kept beside the implementation so the two cannot drift.
READ_ONLY_TOOLS = ("read_deal", "read_criteria", "read_deliverable")


class AgentToolbox:
    """Everything an agent may read about one deal. Nothing it may change."""

    def __init__(
        self,
        *,
        deal_id: uuid.UUID,
        deal_repo: DealRepository,
        deliverable_repo: DeliverableRepository,
    ) -> None:
        self._deal_id = deal_id
        self._deals = deal_repo
        self._deliverables = deliverable_repo

    @property
    def deal_id(self) -> uuid.UUID:
        return self._deal_id

    async def read_deal(self) -> DealContext:
        """The deal's terms: description, amount, currency.

        Deliberately not the parties, the PayPal ids or the state — none of
        that helps judge a deliverable, so none of it is sent.
        """
        deal = await self._deals.get(self._deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        return DealContext(description=deal.description, amount=deal.amount, currency=deal.currency)

    async def read_criteria(self) -> tuple[tuple[str, str], ...]:
        """The confirmed acceptance checklist as (criterion_id, text).

        The ids let the verifier report per criterion, and let the caller
        discard any id the model invents.
        """
        criteria = await self._deals.list_criteria(self._deal_id)
        return tuple((str(criterion.id), criterion.text) for criterion in criteria)

    async def read_deliverable(self) -> DeliverableContext | None:
        """The latest submission, or None if nothing has been submitted.

        The content is untrusted data. It is handed to the agent wrapped in
        an explicit data boundary and with instructions to judge it rather
        than obey it — see `integrations/ai/prompts.py`.
        """
        deliverable = await self._deliverables.get_latest(self._deal_id)
        if deliverable is None:
            return None
        return DeliverableContext(
            type=deliverable.type.value,
            content_ref=deliverable.content_ref,
            note=deliverable.note,
        )
