from issue.envelope import IssuedEnvelope
from issue.register import IssueRegister


def retrieve_piece(register: IssueRegister, issue_id: int) -> IssuedEnvelope:
    return register.read(issue_id)
