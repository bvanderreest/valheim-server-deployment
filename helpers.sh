count_connected_players() {
  # More accurate: track who connected and disconnected
  if [[ ! -f "${LOGFILE}" ]]; then echo "0"; return; fi
  local -A players
  while IFS= read -r line; do
    # Try to match the format with player names: "Player 'PlayerName' connected/disconnected"
    if [[ $line =~ Player\ '([^']+)'\ (connected|disconnected) ]]; then
      local player="${BASH_REMATCH[1]}"
      local action="${BASH_REMATCH[2]}"
      if [[ "${action}" == "connected" ]]; then
        players["${player}"]=1
      else
        unset 'players["${player}"]'
      fi
  done < "${LOGFILE}"
  echo "${#players[@]}"
}