"""Вход выполняется до загрузки архива и запуска любого исследования."""

from __future__ import annotations

import streamlit as st

from .auth import AuthError, AuthStore


def clear_workspace():
    for key in list(st.session_state):
        if not key.startswith("_auth_"):
            del st.session_state[key]


def leave(auth, notice="Вы вышли из учётной записи."):
    token = st.session_state.get("_auth_token")
    if token:
        try:
            auth.logout(token)
        except AuthError:
            st.session_state._auth_pending_logout = token
            st.session_state._auth_logout_error = (
                "Не удалось отозвать сессию. Выход ещё не завершён. Повторите попытку."
            )
            return False
    st.session_state.clear()
    st.session_state._auth_notice = notice
    return True


def _finish_pending_logout(auth):
    if not leave(auth):
        st.error(st.session_state._auth_logout_error)
        st.button("Повторить выход", key="logout_retry", on_click=leave, args=(auth,))
        st.stop()


def expire_access():
    auth = st.session_state.get("_auth_store")
    if auth:
        leave(auth, "Сессия завершена. Войдите снова.")
    else:
        st.session_state.clear()
    st.rerun()


def _login(auth):
    username = st.session_state.get("login_username", "")
    password = st.session_state.get("login_password", "")
    try:
        token = auth.login(username, password)
    except AuthError as exc:
        st.session_state._auth_error = str(exc)
        st.session_state.login_password = ""
    else:
        clear_workspace()
        st.session_state._auth_token = token
        st.session_state.pop("_auth_error", None)
        st.session_state.pop("_auth_notice", None)


@st.fragment(run_every=60)
def _watch(auth, token):
    try:
        auth.resolve(token)
    except AuthError:
        expire_access()


def require_access(path, mode):
    if mode not in {"local", "demo"}:
        st.error("Ошибка конфигурации доступа. Допустимые режимы: local и demo. Обратитесь к администратору.")
        st.stop()
    try:
        auth = AuthStore(path, allow_demo=mode == "demo")
    except AuthError as exc:
        st.error(str(exc))
        st.stop()
    if st.session_state.get("_auth_mode") not in {None, mode}:
        st.session_state.clear()
    st.session_state._auth_mode = mode
    st.session_state._auth_store = auth
    if st.session_state.get("_auth_pending_logout"):
        _finish_pending_logout(auth)
    token = st.session_state.get("_auth_token")
    if token:
        try:
            user = auth.resolve(token, touch=True)
        except AuthError:
            if not leave(auth, "Сессия завершена. Войдите снова."):
                _finish_pending_logout(auth)
            token = None
    if not token and mode == "demo":
        token = auth.create_demo_session()
        st.session_state._auth_token = token
        user = auth.resolve(token)
    if not token:
        left, right = st.columns([1.25, 1], gap="large", vertical_alignment="center")
        with left:
            st.markdown(
                '<div class="login-story"><div class="login-wordmark">двойник</div>'
                "<h1>Исследуйте продукт<br>до запуска</h1>"
                "<p>Сравнивайте предложения на синтетической аудитории, изучайте причины решений "
                "и проверяйте гипотезы живым опросом.</p>"
                '<div class="login-process"><span>Предложения</span><span>Двойники</span><span>Исследование</span></div>'
                "<small>Сохранённые исследования доступны владельцу учётной записи.</small></div>",
                unsafe_allow_html=True,
            )
        with right:
            with st.container(border=True):
                st.subheader("Войти в рабочее пространство")
                st.caption("Учётную запись создаёт администратор вашей команды.")
                with st.form("login_form", border=False):
                    st.text_input("Логин", key="login_username", max_chars=80)
                    st.text_input("Пароль", type="password", key="login_password", max_chars=256)
                    st.form_submit_button(
                        "Войти",
                        key="login_submit",
                        type="primary",
                        width="stretch",
                        on_click=_login,
                        args=(auth,),
                    )
                if st.session_state.get("_auth_error"):
                    st.error(st.session_state._auth_error)
                if st.session_state.get("_auth_notice"):
                    st.info(st.session_state._auth_notice)
                st.caption("Забыли пароль или нет доступа? Обратитесь к администратору.")
        if not auth.users():
            st.info(
                "Первый запуск: создайте администратора на сервере командой python manage.py create-user --username nikita --name Никита --admin. Пароль вводится скрыто."
            )
        st.stop()
    _watch(auth, token)
    return auth, token, user


def account_sidebar(auth, token, user):
    st.sidebar.divider()
    st.sidebar.write(user.name)
    st.sidebar.caption(
        "Демо без входа"
        if user.role == "demo"
        else f"@{user.username} · {'Администратор' if user.role == 'admin' else 'Исследователь'}"
    )
    st.sidebar.button(
        "Обновить скачивания",
        key="refresh_downloads",
        on_click=lambda: st.session_state.pop("_download_cache", None),
        help="Подготовить новые одноразовые ссылки для повторного скачивания отчётов.",
        width="stretch",
    )
    if user.role != "demo":
        pending = bool(st.session_state.get("pending_records"))
        discard = False
        if pending:
            st.sidebar.warning("Есть несохранённые изменения. Скачайте отчёт перед выходом.")
            discard = st.sidebar.checkbox("Завершить без сохранения", key="logout_discard")
        st.sidebar.button(
            "Выйти",
            key="logout",
            on_click=leave,
            args=(auth,),
            disabled=pending and not discard,
            width="stretch",
        )


def administration(auth, token):
    if auth.resolve(token).role != "admin":
        st.error("Раздел доступен администратору.")
        st.stop()
    st.title("Доступ команды")
    st.caption("Управляйте учётными записями. Исследования принадлежат их авторам.")
    for user in auth.users():
        with st.container(border=True):
            info, action = st.columns([3, 1], vertical_alignment="center")
            info.write(f"{user['name']} · @{user['username']}")
            info.caption(
                f"{'Администратор' if user['role'] == 'admin' else 'Исследователь'} · {'Активен' if user['active'] else 'Доступ закрыт'}"
            )
            if action.button(
                "Закрыть доступ" if user["active"] else "Открыть доступ",
                key=f"user_active_{user['id']}",
                width="stretch",
            ):
                try:
                    if auth.resolve(token).role != "admin":
                        expire_access()
                    auth.set_active(user["id"], not user["active"])
                except AuthError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
    with st.expander("Создание аккаунта и смена пароля"):
        st.caption(
            "Выполняется администратором на сервере. Пароль вводится скрыто и не попадает в историю команд."
        )
        st.code(
            "python manage.py create-user --username colleague --name 'Имя коллеги'\npython manage.py reset-password --username colleague",
            language="bash",
        )
