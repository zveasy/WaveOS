from waveos.utils import Principal, Role, Permission, authorize


def test_rbac_permissions() -> None:
    viewer = Principal(name="viewer", role=Role.VIEWER)
    operator = Principal(name="operator", role=Role.OPERATOR)
    admin = Principal(name="admin", role=Role.ADMIN)

    assert authorize(viewer, Permission.VIEW_REPORTS)
    assert not authorize(viewer, Permission.RUN_PIPELINE)
    assert authorize(operator, Permission.RUN_PIPELINE)
    assert authorize(admin, Permission.MODIFY_POLICY)
