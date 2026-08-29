import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Overview } from "@/pages/Overview";
import { NewReconciliation } from "@/pages/NewReconciliation";
import { Processing } from "@/pages/Processing";
import { Results } from "@/pages/Results";
import { Exceptions } from "@/pages/Exceptions";
import { ExceptionDetailPage } from "@/pages/ExceptionDetailPage";
import { AuditLogs } from "@/pages/AuditLogs";
import { History } from "@/pages/History";
import { Settings } from "@/pages/Settings";

export default function App() {
  const location = useLocation();

  return (
    <Routes>
      <Route
        path="/"
        element={
          <Shell title="Overview" routeKey={location.key}>
            <Overview />
          </Shell>
        }
      />
      <Route
        path="/new"
        element={
          <Shell title="New Reconciliation" breadcrumb={["Reconciliation"]} routeKey={location.key}>
            <NewReconciliation />
          </Shell>
        }
      />
      <Route
        path="/processing/:jobId"
        element={
          <Shell title="Processing" breadcrumb={["Reconciliation", "Run"]} routeKey="processing">
            <Processing />
          </Shell>
        }
      />
      <Route
        path="/results/:jobId"
        element={
          <ResultsShell>
            <Results />
          </ResultsShell>
        }
      />
      <Route
        path="/exceptions"
        element={
          <Shell title="Exceptions" breadcrumb={["Reconciliation"]} routeKey={location.key}>
            <Exceptions />
          </Shell>
        }
      />
      <Route
        path="/exceptions/:orderId"
        element={
          <ExceptionShell>
            <ExceptionDetailPage />
          </ExceptionShell>
        }
      />
      <Route
        path="/audit"
        element={
          <Shell title="Audit Logs" breadcrumb={["Reconciliation"]} routeKey={location.key}>
            <AuditLogs />
          </Shell>
        }
      />
      <Route
        path="/history"
        element={
          <Shell title="Reconciliation History" routeKey={location.key}>
            <History />
          </Shell>
        }
      />
      <Route
        path="/settings"
        element={
          <Shell title="Settings" routeKey={location.key}>
            <Settings />
          </Shell>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function Shell({
  title,
  breadcrumb,
  routeKey,
  children,
}: {
  title: string;
  breadcrumb?: string[];
  routeKey: string;
  children: React.ReactNode;
}) {
  return (
    <AppShell title={title} breadcrumb={breadcrumb} routeKey={routeKey}>
      {children}
    </AppShell>
  );
}

function ResultsShell({ children }: { children: React.ReactNode }) {
  const { jobId } = useParams();
  return (
    <AppShell
      title="Reconciliation Results"
      breadcrumb={["Reconciliation", jobId ?? ""]}
      routeKey={`results-${jobId}`}
    >
      {children}
    </AppShell>
  );
}

function ExceptionShell({ children }: { children: React.ReactNode }) {
  const { orderId } = useParams();
  return (
    <AppShell
      title={`Exception ${orderId ?? ""}`}
      breadcrumb={["Reconciliation", "Exceptions"]}
      routeKey={`exception-${orderId}`}
    >
      {children}
    </AppShell>
  );
}
