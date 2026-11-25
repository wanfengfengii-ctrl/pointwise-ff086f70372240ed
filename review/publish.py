from intake.selection import select_pair
from intake.store import IntakeStore
from review.agreement import compute_agreement
from review.store import ReportStore, SignedReport


def review_pair(store: ReportStore, left_id: int, right_id: int) -> SignedReport:
    pair = select_pair(IntakeStore(store.connection), left_id, right_id)
    return store.commit_report(compute_agreement(pair), pair)
