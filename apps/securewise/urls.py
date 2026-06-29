from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogViewSet,
    DashboardSummaryView,
    FindingViewSet,
    GitIntegrationViewSet,
    IntegrationViewSet,
    MembershipViewSet,
    OrganizationViewSet,
    ProjectViewSet,
    ReportViewSet,
    RepositoryViewSet,
    ScanPolicyViewSet,
    ScanViewSet,
)

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="sw-organizations")
router.register("memberships", MembershipViewSet, basename="sw-memberships")
router.register("git-integrations", GitIntegrationViewSet, basename="sw-git-integrations")
router.register("projects", ProjectViewSet, basename="sw-projects")
router.register("repositories", RepositoryViewSet, basename="sw-repositories")
router.register("scan-policies", ScanPolicyViewSet, basename="sw-scan-policies")
router.register("scans", ScanViewSet, basename="sw-scans")
router.register("findings", FindingViewSet, basename="sw-findings")
router.register("reports", ReportViewSet, basename="sw-reports")
router.register("integrations", IntegrationViewSet, basename="sw-integrations")
router.register("audit-logs", AuditLogViewSet, basename="sw-audit-logs")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="sw-dashboard-summary"),
]
