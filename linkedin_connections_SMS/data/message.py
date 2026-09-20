# ============================================================
# YOUR OUTREACH MESSAGE — edit this file to change what gets sent.
#
# HOW TO USE:
#   - Edit the text between the quotes below.
#   - Placeholders (auto-replaced when sending):
#       {name}        -> the full clean name, e.g. "Md. Rakibul Islam"
#       {portfolio}   -> PORTFOLIO_URL from data/.env
#       {headline}    -> the contact's LinkedIn headline (may be empty)
#   - Save the file. The next `python agent.py send` uses it automatically.
#   - Preview any time with: python agent.py message
#   - Keep each line short; "\n" means a line break.
# ============================================================

MESSAGE = (
    "Hi, {name}\n\n"
    "I hope all is well with you. I wanted to let you know I'm currently searching for a job or any project-based work. "
    "If you ever have something I could help with or know of any leads, it would genuinely mean a lot to me right now.\n"
    "To see my work: {portfolio}\n\n"
    "Thank you for taking the time to read this!"
)

# Tip — a personalized opener gets many more replies. Example:
# MESSAGE = (
#     "Hi, {name}\n\n"
#     "Saw your profile — {headline} — and wanted to reach out.\n\n"
#     "I'm currently looking for a job or project-based work. "
#     "If you know of any leads, it would genuinely mean a lot to me right now.\n"
#     "To see my work: {portfolio}\n\n"
#     "Thank you for taking the time to read this!"
# )
