from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .application_views import ApplicationTargetActionView, ApplicationTargetView, TestingAuthorizationView
from .views import (
    AuditLogViewSet,
    DashboardSummaryView,
    FindingViewSet,
    GitHubAppCallbackView,
    GitHubAppConnectView,
    GitHubAppInstallationView,
    GitHubAppRepositorySelectionView,
    GitHubAppWebhookView,
    GitIntegrationViewSet,
    IntegrationViewSet,
    MembershipViewSet,
    OrganizationViewSet,
    PentestSessionViewSet,
    PentestTestProposalViewSet,
    ProjectViewSet,
    ReportViewSet,
    RepositoryViewSet,
    ScanPolicyTemplateViewSet,
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
router.register("scan-policy-templates", ScanPolicyTemplateViewSet, basename="sw-scan-policy-templates")
router.register("scans", ScanViewSet, basename="sw-scans")
router.register("autopentest/sessions", PentestSessionViewSet, basename="sw-pentest-sessions")
router.register("autopentest/proposals", PentestTestProposalViewSet, basename="sw-pentest-proposals")
router.register("findings", FindingViewSet, basename="sw-findings")
router.register("reports", ReportViewSet, basename="sw-reports")
router.register("integrations", IntegrationViewSet, basename="sw-integrations")
router.register("audit-logs", AuditLogViewSet, basename="sw-audit-logs")

urlpatterns = [
    path("", include(router.urls)),
    path("github-app/connect/", GitHubAppConnectView.as_view(), name="sw-github-app-connect"),
    path("github-app/callback/", GitHubAppCallbackView.as_view(), name="sw-github-app-callback"),
    path("github-app/installations/", GitHubAppInstallationView.as_view(), name="sw-github-app-installations"),
    path(
        "github-app/repositories/select/",
        GitHubAppRepositorySelectionView.as_view(),
        name="sw-github-app-repository-selection",
    ),
    path("github-app/webhook/", GitHubAppWebhookView.as_view(), name="sw-github-app-webhook"),
    path("application-targets/", ApplicationTargetView.as_view(), name="sw-application-targets"),
    path(
        "application-targets/<uuid:target_id>/<str:action>/",
        ApplicationTargetActionView.as_view(),
        name="sw-application-target-action",
    ),
    path("testing-authorizations/", TestingAuthorizationView.as_view(), name="sw-testing-authorizations"),
    path(
        "testing-authorizations/<uuid:authorization_id>/revoke/",
        TestingAuthorizationView.as_view(),
        name="sw-testing-authorization-revoke",
    ),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="sw-dashboard-summary"),
]
