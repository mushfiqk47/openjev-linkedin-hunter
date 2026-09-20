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

# General / Fallback message:
MESSAGE = (
    "Hi, {name}\n\n"
    "I hope all is well with you. I wanted to let you know I'm currently searching for a job or any project-based work. "
    "If you ever have something I could help with or know of any leads, it would genuinely mean a lot to me right now.\n"
    "To see my work: {portfolio}\n\n"
    "Thank you for taking the time to read this!"
)

# 1. Recruiter / Talent Acquisition Angle
MESSAGE_RECRUITER = (
    "Hi, {name}\n\n"
    "I hope you're having a productive week. I noticed your background in talent acquisition and recruitment. "
    "I'm an active UI/UX Designer looking for my next full-time or contract product design role.\n\n"
    "If you have any open design roles or upcoming opportunities across your network, I'd love to connect.\n"
    "To view my recent work: {portfolio}\n\n"
    "Thank you for your time, {name}!"
)

# 2. Founder / C-Suite / Executive Angle
MESSAGE_FOUNDER = (
    "Hi, {name}\n\n"
    "Hope all is well. I've been following your venture and wanted to reach out. "
    "I'm a UI/UX Designer helping startups and teams build clean SaaS, web, and mobile interfaces that scale.\n\n"
    "If you're looking for dedicated design support, design system revamps, or project-based help, I'd love to chat.\n"
    "Selected work & case studies: {portfolio}\n\n"
    "Best regards,\nMushfiq"
)

# 3. Peer Designer / Design Lead Angle
MESSAGE_PEER = (
    "Hi, {name}\n\n"
    "Hope all is well with you! Great to connect with a fellow designer. "
    "I'm currently searching for new UI/UX design opportunities and project-based work.\n\n"
    "If your team happens to be hiring or if you know of any design leads, I'd genuinely appreciate a heads-up.\n"
    "To see my work: {portfolio}\n\n"
    "Thanks so much, {name}!"
)
