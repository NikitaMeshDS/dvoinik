import { Login } from "./Account";
import { Brand, Notice, Button } from "./components";
import { useSession } from "./app/useSession";
import Workspace from "./app/Workspace";
export default function App() {
  const auth = useSession();
  if (auth.booting)
    return (
      <div className="boot-screen">
        <Brand />
        <p role="status">Открываем рабочее пространство…</p>
      </div>
    );
  if (!auth.session)
    return <Login onSubmit={auth.login} busy={auth.busy} error={auth.error} />;
  if (auth.logoutBlocked)
    return (
      <div className="boot-screen">
        <Brand />
        <Notice kind="error">{auth.logoutBlocked}</Notice>
        <Button onClick={auth.logout}>Повторить выход</Button>
      </div>
    );
  return (
    <Workspace
      key={auth.session.csrf_token}
      session={auth.session}
      onLogout={auth.logout}
    />
  );
}
