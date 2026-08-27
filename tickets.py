"""
The written analysis for each ticket type: what the merchant says, what is
actually going on, and a first reply worth sending.

This is the hand-written half of the report. Counts, star averages, doc pages and
resolvability all come from the database at build time, so nothing here repeats a
number that could drift. What lives here is judgement, which no query produces.

Draft replies are written to be sent close to as-is. They follow the same shape:
name the specific thing the merchant said, say what is actually happening without
hedging, say what happens next and who does it, and give a time. No apology
padding, no "we value your feedback".
"""

TICKETS = {
    "billing_surprise": {
        "title": "Charged something they did not expect",
        "says": "Scam. Fraudulent billing. I was charged after I uninstalled.",
        "going_on": (
            "Three different problems wearing the same words. Some merchants were "
            "charged correctly under a usage-based plan they never understood. Some "
            "hit Shopify's billing cycle, which does not line up with the app's, so a "
            "charge lands after they thought they had left. A few look like genuine "
            "errors. The reply has to establish which before it can do anything, and "
            "the merchant is furious in all three cases."
        ),
        "reply": (
            "Thanks for flagging this, and I understand why the charge looked wrong.\n\n"
            "I have pulled up your account. The $X on DATE is a usage charge for MONTH, "
            "which covers the orders that went through the cart between DATE and DATE. "
            "Our billing runs on Shopify's cycle rather than ours, which is why it can "
            "arrive after you have stopped using the app.\n\n"
            "If that does not match what you expected to be paying, tell me and I will "
            "get it credited today. If you would rather not be billed again, I can "
            "cancel the subscription from my side right now and confirm when it is "
            "done, so nothing depends on the uninstall going through cleanly."
        ),
    },
    "app_unreliable": {
        "title": "The app broke, or keeps breaking",
        "says": "Full of bugs. Crashes constantly. Brilliant app when it works, which it never did.",
        "going_on": (
            "Mostly genuine faults, and the merchant usually cannot tell you which one. "
            "Fourteen of the nineteen were judged to need engineering; four could not be "
            "decided from the review at all, because 'buggy' does not distinguish a "
            "defect from a theme conflict. The ticket that arrives will be this vague, "
            "so the first reply's job is to turn it into something reproducible."
        ),
        "reply": (
            "Sorry, that sounds genuinely disruptive. I want to get this reproduced today "
            "rather than trade guesses.\n\n"
            "Three things and I can usually pin it down: which page it happens on, what "
            "you click just before it goes wrong, and whether it happens in an incognito "
            "window too. A screen recording is faster than all three if you have one.\n\n"
            "I will test it against your theme on my side in parallel. If it turns out to "
            "be our bug I will get it in front of engineering with the reproduction "
            "attached, and I will tell you either way by END OF DAY rather than leaving "
            "you waiting."
        ),
    },
    "theme_or_styling_conflict": {
        "title": "Does not fit their theme",
        "says": "Not compatible with the Horizon theme. Colours will not change. It broke our layout.",
        "going_on": (
            "The most fixable category in the set. Eleven of thirteen were resolvable by "
            "support directly, and the reviews that praise this app hardest are often the "
            "same problem with a different ending: a merchant who got custom CSS within "
            "the hour. This is the ticket type where writing code in the reply is the job."
        ),
        "reply": (
            "That is fixable and I can usually do it in the conversation.\n\n"
            "Send me your store URL and a screenshot with the problem circled. Most theme "
            "conflicts come down to the theme's own cart styles overriding ours, and I can "
            "write the CSS to override it back and paste it in for you to apply.\n\n"
            "If it turns out to be deeper than styling, say the drawer not opening at all "
            "on your theme, I will tell you that straight rather than send you round in "
            "circles with snippets."
        ),
    },
    "support_experience": {
        "title": "Could not get help, or the help did not help",
        "says": "Three hours in the support chat with zero replies. The AI bot did not understand. Copy-paste answers.",
        "going_on": (
            "The complaint is the queue itself, not the product. Several name the chatbot "
            "specifically as the barrier, and several name the moment a human arrived as "
            "the moment it got fixed. This is also the type with no documentation at all: "
            "nothing in 265 pages says how to reach a person, what response times to "
            "expect, or how to escalate."
        ),
        "reply": (
            "You waited far too long for that, and I am sorry. I am a person and I am on "
            "it now.\n\n"
            "Tell me what you were originally trying to do and I will pick it up from "
            "there rather than making you repeat the whole thing to someone new.\n\n"
            "For anything urgent in future you can reach me directly at EMAIL and skip the "
            "chat queue entirely."
        ),
    },
    "feature_request": {
        "title": "Wants something the app does not do",
        "says": "Great app. I wish it also did X.",
        "going_on": (
            "Not a complaint, and it matters that the triage sheet says so. These average "
            "4.5 stars: satisfied merchants asking for more. They were counted separately "
            "from merchants the same gap actually cost, because merging the two makes the "
            "queue look angrier than it is and buries the people who are leaving."
        ),
        "reply": (
            "Glad it is working well for you, and thank you for the specific ask, that is "
            "more useful than it probably feels.\n\n"
            "MULTI-LANGUAGE is not something the app does today. I have logged it with the "
            "detail you gave, which is what makes a request actually get looked at rather "
            "than counted.\n\n"
            "In the meantime WORKAROUND gets you part of the way. Happy to set that up with "
            "you if it would help."
        ),
    },
    "capability_gap": {
        "title": "The missing feature cost them something",
        "says": "Do not use this if you have multiple languages. This is a cross-sell app, not an upsell app.",
        "going_on": (
            "The same absences as a feature request, but these merchants downgraded, left, "
            "or could not launch. Average 2.8 stars against 4.5. Support cannot fix any of "
            "it, and pretending otherwise wastes everyone's time. What support can do is be "
            "straight about it fast enough that the merchant can make a decision."
        ),
        "reply": (
            "You are right, and I would rather tell you that plainly than keep you looking "
            "for a setting that does not exist.\n\n"
            "The app does not do MULTI-LANGUAGE today. WORKAROUND covers some of it, with "
            "the limits you have already hit. If that is not enough for your store, it is "
            "not enough, and I will not talk you round.\n\n"
            "I have logged this against your account so it carries weight when the roadmap "
            "gets set. If you would like to stop your subscription while you wait, tell me "
            "and I will handle it without the usual back and forth."
        ),
    },
    "third_party_integration_broken": {
        "title": "Broke something outside the app",
        "says": "Klaviyo stopped seeing add-to-cart. Analytics double counting. Meta ads attribution gone.",
        "going_on": (
            "Every one of these is a one-star review. The mean rating is 1.7 and no review "
            "in the category rates higher. The reason is that the damage is invisible for "
            "weeks, gets discovered late, and is measured in lost revenue rather than "
            "annoyance. One merchant describes weeks of work to trace it. The docs cover "
            "the Klaviyo case under a findable title but bury the analytics case under "
            "'Conversion tracking (web pixels)', which nobody searches for."
        ),
        "reply": (
            "This is a known interaction and you should not have had to find it yourself.\n\n"
            "Installing the cart drawer changes how add-to-cart events fire, which is why "
            "TOOL stopped seeing them. There is a fix and I will apply it with you now "
            "rather than sending you a code snippet without context: DOC LINK.\n\n"
            "Two things beyond that. I can help you check whether the affected period needs "
            "correcting on TOOL's side, and I am flagging internally that this is not "
            "surfaced at install, because you are not the first."
        ),
    },
    "unexpected_order_change": {
        "title": "The app changed a customer's order",
        "says": "A product was added to their order without consent. Charged twice. I got a chargeback.",
        "going_on": (
            "Six reviews, and the most serious type in the set. A merchant here is not "
            "annoyed about a feature, they are dealing with their own customers and "
            "possibly their payment provider. One reports being able to reproduce it, "
            "which is the strongest evidence in the dataset. Nothing in the documentation "
            "addresses it. Treat as an incident, not a ticket."
        ),
        "reply": (
            "Thank you for telling us, and I am treating this as urgent.\n\n"
            "Send me one affected order number. I will trace what the app did on that order "
            "and confirm within the hour whether we caused it. If we did, I will get it to "
            "engineering immediately and stay on it rather than handing you off.\n\n"
            "While we work that out I can disable the post-purchase offers on your store so "
            "no further orders are affected. Say the word and it is off in two minutes. If "
            "you are dealing with chargebacks I can put the timeline in writing for your "
            "payment provider."
        ),
    },
}
