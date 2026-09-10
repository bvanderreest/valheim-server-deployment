"""Player count, from the log the live server actually wrote.

The operator joined the game and the Portal kept saying nobody was on. The old
parser counted "Server: New peer connected" and subtracted "RPC_Disconnect",
which assumes the two always pair up. A join that fails the password check logs
a disconnect and never logs a connect, so one failed attempt permanently offset
the count for the rest of the session.

Every line below is verbatim from /srv/valheim/logs/valheim-server.log,
2026-09-10, including the failed attempt that caused it.
"""
import pytest

from api.routes import server as srv

SESSION = """09/10/2026 09:44:02: Valheim version: l-1.0.7 (network version 39)
09/10/2026 09:51:29:  Connections 0 ZDOS:419858  sent:0 recv:0
09/10/2026 09:58:12: PlayFab listen socket child connected to remote player DBC9329C0FB021F9
09/10/2026 09:58:12: Player joined server "Lowood-AU" that has join code 375598, now 1 player(s)
09/10/2026 09:58:12: Muted PlayFab remote player DBC9329C0FB021F9
09/10/2026 09:58:12: Got handshake from client playfab/DBC9329C0FB021F9
09/10/2026 09:58:21: Peer playfab/DBC9329C0FB021F9 has wrong password
09/10/2026 09:58:21: RPC_Disconnect
09/10/2026 09:58:21: Player connection lost server "Lowood-AU" that has join code 375598, now 0 player(s)
09/10/2026 09:58:59: PlayFab listen socket child connected to remote player DBC9329C0FB021F9
09/10/2026 09:58:59: Player joined server "Lowood-AU" that has join code 375598, now 1 player(s)
09/10/2026 09:58:59: Got handshake from client playfab/DBC9329C0FB021F9
09/10/2026 09:59:05: Server: New peer connected,sending global keys
09/10/2026 09:59:25: Got character ZDOID from Getge : 498541589:1
09/10/2026 10:01:30:  Connections 1 ZDOS:419859  sent:0 recv:410
""".splitlines(keepends=True)


@pytest.fixture
def log(tmp_path, monkeypatch):
    def _write(lines):
        f = tmp_path / "valheim-server.log"
        f.write_text("".join(lines))
        monkeypatch.setattr(srv.settings, "_logfile", f, raising=False)
        return f
    return _write


def test_a_player_who_is_on_is_counted(log):
    """The reported bug. One failed password attempt made the count 0 while a
    player was stood in the world."""
    log(SESSION)
    info = srv._get_player_info()
    assert info.count == 1, "the player who joined is not being counted"
    assert info.names == ["Getge"]


def test_the_count_and_the_names_never_contradict(log):
    """The live API returned count=0 with names=['Getge']. A count and a name
    list that disagree are one inference and one observation, not two facts."""
    log(SESSION)
    info = srv._get_player_info()
    assert bool(info.names) == (info.count > 0), (
        f"count={info.count} but names={info.names}")


def test_leaving_clears_the_name(log):
    """`<name> : 0:0` is a character with no ZDO — logged out or dead. The old
    parser skipped that line, so names accumulated for the whole session."""
    left = SESSION + [
        '09/10/2026 10:05:00: Got character ZDOID from Getge : 0:0\n',
        '09/10/2026 10:05:01: Player connection lost server "Lowood-AU" that has join code 375598, now 0 player(s)\n',
    ]
    log(left)
    info = srv._get_player_info()
    assert info.count == 0
    assert info.names == []


def test_a_failed_password_attempt_alone_does_not_go_negative(log):
    """Just the failed attempt, no successful join."""
    log(SESSION[:9])
    info = srv._get_player_info()
    assert info.count == 0
    assert info.names == []


def test_a_second_player_is_counted(log):
    two = SESSION + [
        '09/10/2026 10:10:00: Player joined server "Lowood-AU" that has join code 375598, now 2 player(s)\n',
        '09/10/2026 10:10:04: Server: New peer connected,sending global keys\n',
        '09/10/2026 10:10:09: Got character ZDOID from Hrafn : 498541590:1\n',
    ]
    log(two)
    info = srv._get_player_info()
    assert info.count == 2
    assert info.names == ["Getge", "Hrafn"]


# ── the reconnect grace window ───────────────────────────────────────────────
# Found by re-reading the log after the session ended. The player quit, and the
# server went on reporting them:
#
#   10:08:56  Keep socket for playfab/... , try to reconnect before timeout
#   10:08:56  Player connection lost ... now 1 player(s)      <- still 1
#   10:08:57  Destroying abandoned non persistent zdo 498541589:1 owner ...
#
# So "trust the server's tally" was necessary but not sufficient: the tally
# counts sockets, and a socket outlives the player who left.

LEFT_BUT_SOCKET_HELD = SESSION + [
    '09/10/2026 10:08:56: Keep socket for playfab/AAAA1111BBBB2222, try to reconnect before timeout\n',
    '09/10/2026 10:08:56: Player connection lost server "Lowood-AU" that has join code 123456, now 1 player(s)\n',
    '09/10/2026 10:08:56: RPC_Disconnect\n',
    '09/10/2026 10:08:57: Destroying abandoned non persistent zdo 498541589:1 owner 498541589\n',
]


def test_a_held_socket_does_not_keep_a_departed_player_on_the_board(log):
    """The server still says 'now 1 player(s)'. Nobody is playing."""
    log(LEFT_BUT_SOCKET_HELD)
    info = srv._get_player_info()
    assert info.count == 0, "a socket held open for reconnect is being counted as a player"
    assert info.names == []


def test_someone_connected_but_not_yet_spawned_still_counts(log):
    """The socket tally is the only evidence before a character exists, so it
    must not be discarded outright."""
    joining = [
        '09/10/2026 09:44:02: Valheim version: l-1.0.7 (network version 39)\n',
        '09/10/2026 09:58:59: Player joined server "Lowood-AU" that has join code 123456, now 1 player(s)\n',
        '09/10/2026 09:59:05: Server: New peer connected,sending global keys\n',
    ]
    log(joining)
    info = srv._get_player_info()
    assert info.count == 1
    assert info.names == []
