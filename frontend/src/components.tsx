import {
  useEffect,
  useRef,
  type ReactNode,
  type ButtonHTMLAttributes,
} from "react";
import { MoreHorizontal, X, ArrowRight, ChevronLeft } from "lucide-react";
export function Button({
  children,
  kind = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: string }) {
  return (
    <button
      {...props}
      className={"button " + kind + " " + (props.className ?? "")}
    >
      {children}
    </button>
  );
}
export function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
      </span>
      <span>двойник</span>
    </span>
  );
}
export function Back({
  onClick,
  children = "Исследования",
}: {
  onClick: () => void;
  children?: ReactNode;
}) {
  return (
    <button className="back-link" onClick={onClick}>
      <ChevronLeft size={17} />
      {children}
    </button>
  );
}
export function Heading({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-orbit" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Menu({
  label = "Ещё",
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function dismiss(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        ref.current.open = false;
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);
  return (
    <details
      className="menu"
      ref={ref}
      onKeyDown={(e) => {
        if (e.key === "Escape" && ref.current) {
          ref.current.open = false;
          ref.current.querySelector("summary")?.focus();
        }
      }}
    >
      <summary aria-label={label}>
        <MoreHorizontal size={20} />
      </summary>
      <div
        className="menu-panel"
        onClick={() => {
          if (ref.current) {
            ref.current.open = false;
            ref.current.querySelector("summary")?.focus();
          }
        }}
      >
        {children}
      </div>
    </details>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Закрыть" onClick={onClose}>
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Next({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <ArrowRight size={17} />
    </>
  );
}
export function Notice({
  children,
  kind = "",
}: {
  children: ReactNode;
  kind?: string;
}) {
  return (
    <div
      className={"notice " + kind}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
export { date } from "./data";
export function percent(value: number | null, digits = 1) {
  return value === null ? "—" : (value * 100).toFixed(digits) + "%";
}
