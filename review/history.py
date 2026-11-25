from review.store import ReportStore, SignedReport


def read_report(store: ReportStore, report_id: int) -> SignedReport:
    return store.read(report_id)
