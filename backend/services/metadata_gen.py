"""YouTube metadata generation from transcript segments.

Uses NLP techniques (TF-IDF, named entity extraction, topic segmentation)
to generate SEO-optimized descriptions, chapter timestamps, and tags
from raw transcript data — no external LLM required.
"""

import re
import math
from collections import Counter


# ---------------------------------------------------------------------------
# Filler / greeting / low-content detection
# ---------------------------------------------------------------------------

_FILLER_RE = re.compile(
    r"^(so|okay|alright|um|uh|hey|hi|hello|welcome|yo|yeah|yes|no|"
    r"right|exactly|absolutely|totally|definitely|true|sure|"
    r"cool|nice|wow|dude|man|oh|huh|hmm|ah|"
    r"very cool|that's cool|that's awesome|that's crazy|that's sick|"
    r"that's great|that's really cool|that's really interesting|"
    r"i love that|i love it|i love hearing|love to hear|"
    r"hell yeah|heck yeah|for sure|of course|one hundred percent|"
    r"a hundred percent|one million percent|"
    r"thank you|thanks|appreciate|cheers)\b",
    re.IGNORECASE,
)

_CONVERSATIONAL_FILLER = {
    "yeah", "yes", "no", "right", "exactly", "absolutely", "totally",
    "definitely", "true", "sure", "cool", "nice", "wow", "okay",
    "dude", "man", "oh", "huh", "hmm", "interesting",
}

# Words that never belong in generated titles, tags, or description hooks
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out",
    "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "because", "but",
    "and", "or", "if", "while", "about", "up", "it", "its", "i", "me",
    "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "this", "that", "these", "those", "what",
    "which", "who", "whom", "also", "back", "still", "even", "much",
    "many", "like", "just", "really", "actually", "basically", "literally",
    "kind", "sort", "something", "stuff", "things", "thing", "gonna",
    "people", "think", "know", "right", "yeah", "okay", "well", "want",
    "need", "make", "take", "come", "look", "give", "tell", "talk", "get",
    "got", "said", "say", "going", "went", "done", "doing", "been",
    "made", "let", "put", "way", "time", "now", "good", "lot", "bit",
    "whole", "part", "called", "first", "last", "next", "new", "one",
    "two", "three", "long", "big", "little", "start", "started",
    "work", "worked", "working", "built", "build", "building",
    "cool", "awesome", "amazing", "great", "love", "pretty", "super",
    "feel", "feeling", "guess", "maybe", "probably", "able",
    "don't", "doesn't", "didn't", "won't", "wouldn't", "couldn't",
    "shouldn't", "can't", "isn't", "aren't", "wasn't", "weren't",
    "i'm", "you're", "he's", "she's", "it's", "we're", "they're",
    "i've", "you've", "we've", "they've", "i'd", "you'd", "he'd",
    "she'd", "we'd", "they'd", "i'll", "you'll", "he'll", "she'll",
    "we'll", "they'll", "let's", "that's", "who's", "what's",
    "here's", "there's", "person", "guys", "everybody", "everyone",
}


def _is_low_content(text: str) -> bool:
    """True if segment is filler, greeting, backchannel, or too short."""
    clean = text.strip().rstrip(".,!?")
    if len(clean) < 15:
        return True
    words = clean.lower().split()
    if len(words) <= 3:
        return True
    if _FILLER_RE.match(clean):
        # Check if it's ONLY filler (short filler response)
        if len(words) <= 6:
            return True
    # Mostly filler words?
    filler_count = sum(1 for w in words if w.rstrip(".,!?") in _CONVERSATIONAL_FILLER)
    if filler_count / len(words) > 0.6:
        return True
    return False


# ---------------------------------------------------------------------------
# Named entity / proper noun extraction
# ---------------------------------------------------------------------------

def _extract_entities(segments: list) -> dict:
    """Extract proper nouns and multi-word named entities from segments.

    Returns dict mapping entity string -> count of occurrences.
    Uses capitalization patterns and also finds entities connected by
    common words like "and", "of", "the" (e.g., "Gods and Chain").
    """
    entities = Counter()
    skip_words = {
        "I", "So", "And", "But", "The", "This", "That", "Yeah", "Yes",
        "No", "Like", "Well", "Just", "Also", "Very", "Oh", "Really",
        "Actually", "Basically", "Because", "Right", "Okay", "Hey",
        "What", "How", "Why", "When", "Where", "Who", "Which",
        "If", "Or", "Not", "My", "We", "He", "She", "It", "They",
        "His", "Her", "Our", "Your", "Their", "There", "Here",
        "Some", "Any", "All", "Each", "Every", "Been", "Have",
        "Has", "Had", "Was", "Were", "Are", "Will", "Would", "Could",
        "Should", "Do", "Does", "Did", "Can", "May", "Might",
        "Thank", "Thanks", "Cool", "Nice", "Awesome", "Amazing",
        "Great", "Good", "Exactly", "Absolutely", "Definitely",
        "Another", "First", "Last", "Next", "New", "Old",
    }
    # Small connecting words that can appear between proper noun parts
    connectors = {"and", "of", "the", "for", "in", "on", "at", "de"}
    # Phrases that look like entities but aren't
    skip_phrases = {"with fiat", "the time", "the moment", "the game",
                    "the idea", "the plan", "at the", "on the"}

    for seg in segments:
        text = seg["text"]
        words = text.split()

        # Find extended proper noun phrases (Cap word [connector] Cap word...)
        i = 0
        while i < len(words):
            w = re.sub(r'[^A-Za-z0-9\'-]', '', words[i])
            if w and w[0].isupper() and w not in skip_words and len(w) >= 3:
                # Start of potential entity
                phrase_parts = [w]
                j = i + 1
                while j < len(words):
                    next_w = re.sub(r'[^A-Za-z0-9\'-]', '', words[j])
                    if not next_w:
                        break
                    if next_w[0].isupper() and next_w not in skip_words:
                        phrase_parts.append(next_w)
                        j += 1
                    elif next_w.lower() in connectors and j + 1 < len(words):
                        # Check if word after connector is also capitalized
                        after = re.sub(r'[^A-Za-z0-9\'-]', '', words[j + 1])
                        if after and after[0].isupper() and after not in skip_words:
                            phrase_parts.append(next_w.lower())
                            phrase_parts.append(after)
                            j += 2
                        else:
                            break
                    else:
                        break

                if len(phrase_parts) >= 2:
                    entity = " ".join(phrase_parts)
                    if entity.lower() not in skip_phrases:
                        entities[entity] += 1
                    i = j
                    continue
                else:
                    # Single capitalized word - only count if not sentence-start
                    if i > 0 and w.lower() not in _STOP_WORDS:
                        entities[w] += 1
            i += 1

    return entities


def _extract_entities_in_range(segments: list, start_idx: int, end_idx: int) -> Counter:
    """Extract entities from a slice of segments."""
    return _extract_entities(segments[start_idx:end_idx])


# ---------------------------------------------------------------------------
# TF-IDF keyword scoring
# ---------------------------------------------------------------------------

def _compute_tfidf(segments: list, n_chunks: int = 10) -> list:
    """Compute TF-IDF scores for words across transcript chunks.

    Splits transcript into n_chunks and computes IDF across them.
    Returns list of (word, score) sorted by score descending.
    """
    # Split segments into chunks
    chunk_size = max(1, len(segments) // n_chunks)
    chunks = []
    for i in range(0, len(segments), chunk_size):
        text = " ".join(s["text"] for s in segments[i:i + chunk_size]).lower()
        words = set(re.findall(r'\b[a-z]{4,}\b', text))
        words -= _STOP_WORDS
        chunks.append(words)

    if not chunks:
        return []

    # IDF: log(N / df) where df = number of chunks containing the word
    n_docs = len(chunks)
    df = Counter()
    for chunk_words in chunks:
        for w in chunk_words:
            df[w] += 1

    # TF across full text
    full_text = " ".join(s["text"] for s in segments).lower()
    all_words = re.findall(r'\b[a-z]{4,}\b', full_text)
    tf = Counter(w for w in all_words if w not in _STOP_WORDS)

    # TF-IDF score
    scores = {}
    for word, freq in tf.items():
        if word in df:
            idf = math.log(n_docs / df[word]) + 1  # smoothed IDF
            # Normalize TF by total words
            tf_norm = freq / len(all_words) if all_words else 0
            scores[word] = tf_norm * idf * freq  # boost by raw freq too

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Topic segmentation for chapters
# ---------------------------------------------------------------------------

def _segment_topics(segments: list, target_chapters: int) -> list:
    """Find topic boundary indices using entity density shifts.

    Strategy:
    1. Slide a window across segments and track which entities appear
    2. When the entity set changes significantly, mark a boundary
    3. Also consider pauses and transitional phrases
    """
    if len(segments) < 10:
        return []

    window = max(5, len(segments) // (target_chapters * 2))

    # Precompute entity sets for each window position
    entity_windows = []
    for i in range(len(segments)):
        start = max(0, i - window)
        end = min(len(segments), i + window)
        text = " ".join(s["text"] for s in segments[start:end]).lower()
        # Get distinctive words (not stop words, 5+ chars)
        words = set(re.findall(r'\b[a-z]{5,}\b', text)) - _STOP_WORDS
        entity_windows.append(words)

    # Score each segment as a potential boundary
    scores = []
    for i in range(1, len(segments)):
        score = 0.0

        # Vocabulary shift (Jaccard distance)
        if entity_windows[i - 1] and entity_windows[i]:
            prev_w = entity_windows[max(0, i - window)]
            curr_w = entity_windows[min(len(segments) - 1, i + window // 2)]
            if prev_w and curr_w:
                intersection = prev_w & curr_w
                union = prev_w | curr_w
                if union:
                    jaccard_dist = 1.0 - (len(intersection) / len(union))
                    score += jaccard_dist * 3.0

        # Gap score
        gap = segments[i]["start"] - segments[i - 1]["end"]
        if gap > 3.0:
            score += 2.0
        elif gap > 1.5:
            score += 1.2
        elif gap > 0.8:
            score += 0.5

        # Transition phrase detection
        text_lower = segments[i]["text"].lower()
        if any(p in text_lower for p in [
            "let's talk", "moving on", "another thing", "next topic",
            "speaking of", "switching to", "i also want", "tell us",
            "i'd love to", "let me tell", "the idea for", "the plan",
            "so basically", "from there", "and then from",
            "what about", "how did you", "can you tell",
        ]):
            score += 2.0

        # New speaker / question detection
        if text_lower.rstrip().endswith("?"):
            score += 0.8

        scores.append((i, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def _generate_section_title(segments: list, start_idx: int, end_idx: int,
                            global_entities: dict) -> str:
    """Generate a descriptive chapter title from a section of segments.

    Constructs a clean topic label from the most distinctive entities
    in this section. Avoids using raw transcript quotes.
    """
    section_segs = segments[start_idx:end_idx]
    section_text = " ".join(s["text"] for s in section_segs)

    # Get entities in this section
    section_entities = _extract_entities(section_segs)

    # Find entities concentrated in this section vs global distribution
    section_len = len(section_segs)
    total_len = max(len(segments), 1)

    distinctive_entities = []
    for entity, count in section_entities.most_common(20):
        global_count = global_entities.get(entity, count)
        expected = global_count * (section_len / total_len)
        concentration = count / max(expected, 0.5) if expected > 0 else count
        if concentration > 1.0 and count >= 1:
            distinctive_entities.append((entity, concentration * count))

    distinctive_entities.sort(key=lambda x: x[1], reverse=True)

    # Also get distinctive content words
    section_words_lower = re.findall(r'\b[a-z]{5,}\b', section_text.lower())
    section_word_freq = Counter(w for w in section_words_lower if w not in _STOP_WORDS)
    top_content_words = [w for w, c in section_word_freq.most_common(8) if c >= 2]

    # Strategy: build a topic label (NOT a transcript quote)
    if distinctive_entities:
        top_entities = [e for e, _ in distinctive_entities[:3]]

        # Try to determine what the section is ABOUT using entity + context words
        topic = _build_topic_label(top_entities, top_content_words, section_segs)
        if topic:
            return topic

        # Simple entity-based title
        if len(top_entities) >= 2:
            return f"{top_entities[0]} and {top_entities[1]}"
        return top_entities[0]

    # No entities — use content words to find a topic
    if top_content_words:
        return _build_topic_from_words(top_content_words, section_segs)

    return "Discussion"


def _build_topic_label(entities: list, content_words: list, section_segs: list) -> str:
    """Build a clean topic label from entities and content words.

    Instead of quoting transcript, constructs a descriptive label like:
    "Gods and Chain Tournament Platform" or "Getting Started on Farcaster"
    """
    if not entities:
        return ""

    main_entity = entities[0]

    # Look for a descriptive context around the main entity
    # Check what content words co-occur with this entity
    context_clues = []
    main_lower = main_entity.lower()

    for seg in section_segs:
        text_lower = seg["text"].lower()
        if main_lower not in text_lower:
            continue
        words = text_lower.split()
        for w in words:
            clean = re.sub(r'[^a-z]', '', w)
            if clean and len(clean) > 4 and clean not in _STOP_WORDS:
                context_clues.append(clean)

    clue_freq = Counter(context_clues)
    top_clues = [w for w, c in clue_freq.most_common(5)]

    # Build label patterns based on detected context
    topic_patterns = {
        "tournament": f"{main_entity} Tournaments",
        "tournaments": f"{main_entity} Tournaments",
        "gaming": f"{main_entity} Gaming",
        "agent": f"AI Agents and {main_entity}",
        "agents": f"AI Agents and {main_entity}",
        "ecosystem": f"The {main_entity} Ecosystem",
        "wallet": f"{main_entity} Wallet Integration",
        "trading": f"Trading on {main_entity}",
        "hackathon": f"{main_entity} Hackathon",
        "launch": f"Launching {main_entity}",
        "launched": f"Launching {main_entity}",
        "community": f"{main_entity} Community",
        "deliberation": f"Agent Deliberation in {main_entity}",
        "deliberate": f"Agent Deliberation",
        "cards": f"{main_entity} Card System",
        "promotion": f"Promotion with {main_entity}",
        "growth": f"{main_entity} Growth",
        "users": f"{main_entity} User Growth",
        "profile": f"{main_entity} Profiles",
        "decentralized": f"Decentralized {main_entity}",
        "social": f"{main_entity} and Social",
        "crypto": f"{main_entity} in Crypto",
        "career": f"Career Journey to {main_entity}",
        "journey": f"Journey into {main_entity}",
        "vision": f"Vision for {main_entity}",
    }

    for clue in top_clues:
        if clue in topic_patterns:
            return topic_patterns[clue]

    # If we have 2+ entities, combine them
    if len(entities) >= 2:
        return f"{entities[0]} and {entities[1]}"

    # Just use the entity with a descriptor if available
    if top_clues:
        descriptor = top_clues[0].title()
        return f"{main_entity} {descriptor}"

    return main_entity


def _build_topic_from_words(content_words: list, section_segs: list) -> str:
    """Build a topic label when no named entities are found."""
    # Try to find the most meaningful phrase
    topic_mapping = {
        "agents": "AI Agents",
        "agent": "AI Agents",
        "gaming": "Web3 Gaming",
        "tournament": "Tournament Platform",
        "wallet": "Wallet Integration",
        "crypto": "Crypto Journey",
        "building": "Building in Web3",
        "decentralized": "Decentralized Systems",
        "social": "Social Platform",
        "deliberation": "Agent Deliberation",
        "prediction": "Prediction Markets",
        "community": "Community Building",
        "competitive": "Competitive Integrity",
        "distribution": "Distribution and Growth",
        "collaborative": "Collaborative Building",
        "entertainment": "Entertainment and AI",
    }

    for word in content_words:
        if word in topic_mapping:
            return topic_mapping[word]

    if len(content_words) >= 2:
        return f"{content_words[0].title()} and {content_words[1].title()}"
    if content_words:
        return content_words[0].title()

    return "Discussion"


def _find_best_sentence(segments: list) -> str:
    """Find the most content-rich sentence in a set of segments.

    Prefers sentences with proper nouns and low filler word ratio.
    """
    best = ""
    best_score = -1

    for seg in segments:
        if _is_low_content(seg["text"]):
            continue
        text = seg["text"].strip()
        words = text.split()
        if len(words) < 5:
            continue

        # Score: proper nouns + long words - filler words
        score = 0
        for w in words:
            clean = re.sub(r'[^A-Za-z]', '', w)
            if not clean:
                continue
            if clean[0].isupper() and len(clean) > 2:
                score += 2  # proper noun
            elif len(clean) > 6 and clean.lower() not in _STOP_WORDS:
                score += 1  # substantive word
            elif clean.lower() in _CONVERSATIONAL_FILLER:
                score -= 1

        if score > best_score:
            best_score = score
            best = text

    return best


def _truncate_title(text: str, max_words: int = 8) -> str:
    """Clean and truncate text into a chapter title."""
    text = text.strip()

    # Remove leading filler
    for prefix in ["so ", "and ", "but ", "now ", "okay ", "alright ",
                    "um ", "uh ", "like ", "basically ", "well ",
                    "you know ", "i think ", "i mean ", "yeah ",
                    "and then ", "so then ", "from there "]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]

    # Remove trailing punctuation
    text = text.rstrip(".,!?;:-")

    # Truncate to max words at a natural break
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
        text = text.rstrip(".,!?;:-")

    # Capitalize first letter
    if text:
        text = text[0].upper() + text[1:]

    return text


def _format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS or H:MM:SS."""
    t = int(seconds)
    h = t // 3600
    m = (t % 3600) // 60
    s = t % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_description(segments: list, project_name: str) -> str:
    """Generate a YouTube-optimized description.

    Structure per best practices:
    1. Hook (first 150 chars — appears in search/suggested)
    2. Summary paragraph with key topics/entities
    3. Closing with duration and chapter prompt
    """
    if not segments:
        return f"Full discussion from {project_name}."

    total_duration = segments[-1]["end"]
    duration_mins = int(total_duration / 60)

    # Extract entities and TF-IDF keywords
    entities = _extract_entities(segments)
    tfidf = _compute_tfidf(segments)

    # Get top entities (proper nouns, names, products)
    top_entities = [e for e, c in entities.most_common(15) if c >= 2]
    top_keywords = [w for w, s in tfidf[:20]]

    # Detect guest/host pattern (look for intro phrases)
    guest_name = _detect_guest(segments)
    show_name = _detect_show_name(segments)

    # Build hook (first 150 chars — most important for SEO)
    if guest_name and show_name:
        hook = f"{guest_name} joins {show_name} to discuss"
    elif guest_name:
        hook = f"{guest_name} shares"
    else:
        hook = f"In this episode, we discuss"

    # Find the main topics from entities
    topic_entities = [e for e in top_entities if e.lower() != guest_name.lower()] if guest_name else top_entities
    if topic_entities:
        main_topics = topic_entities[:3]
        hook += " " + ", ".join(main_topics)
        if len(topic_entities) > 3:
            hook += ", and more"
        hook += "."
    elif top_keywords:
        hook += " " + ", ".join(top_keywords[:3]) + ", and more."
    else:
        hook += " a range of topics."

    lines = [hook, ""]

    # Summary paragraph: constructed from entities, not raw transcript quotes
    summary = _build_description_summary(segments, top_entities, guest_name)
    if summary:
        lines.append(summary)
        lines.append("")

    # Topic list (deduplicated, no generic words)
    all_topics = list(dict.fromkeys(top_entities))
    # Add TF-IDF words that aren't already covered by entities
    entity_words = set(w.lower() for e in top_entities for w in e.split())
    for w, _ in tfidf[:10]:
        if w not in entity_words and w not in _STOP_WORDS and len(w) > 4:
            all_topics.append(w.title())
    if all_topics:
        lines.append("Topics covered: " + ", ".join(all_topics[:10]) + ".")
        lines.append("")

    # Closing
    lines.append(
        f"Full {duration_mins}-minute conversation. "
        "Timestamps below for easy navigation."
    )

    return "\n".join(lines)


def _detect_guest(segments: list) -> str:
    """Try to detect the guest's name from intro patterns."""
    # Look in first 20 segments for introduction patterns
    intro_text = " ".join(s["text"] for s in segments[:20])

    patterns = [
        r"(?:I'm here with|joined by|welcome)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:how are you doing today),?\s+([A-Z][a-z]+)",
        r"(?:is that how I pronounce it|you got it).*?([A-Z][a-z]{3,})",
        r"(?:thank you for joining|thanks for joining|thanks for popping in),?\s+([A-Z][a-z]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, intro_text)
        if match:
            name = match.group(1).strip()
            if name.lower() not in _STOP_WORDS and len(name) > 2:
                return name

    # Fallback: find the most mentioned capitalized name in first 20 segments
    entities = _extract_entities(segments[:20])
    for entity, count in entities.most_common(5):
        if count >= 2 and len(entity.split()) == 1 and len(entity) > 3:
            return entity

    return ""


def _detect_show_name(segments: list) -> str:
    """Try to detect the show/podcast name from intro."""
    intro_text = " ".join(s["text"] for s in segments[:10])
    patterns = [
        r"(?:another|welcome to|this is|episode of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, intro_text)
        if match:
            name = match.group(1).strip()
            if name.lower() not in _STOP_WORDS and len(name) > 3:
                return name
    return ""


def _build_description_summary(segments: list, top_entities: list,
                               guest_name: str) -> str:
    """Build a summary paragraph describing what's covered.

    Constructs sentences from detected entities and topics rather
    than quoting raw transcript text.
    """
    if not top_entities:
        return ""

    parts = []

    # Group entities by what they represent
    # Look for what context words surround them to categorize
    entity_contexts = {}
    for entity in top_entities[:8]:
        entity_lower = entity.lower()
        context_words = []
        for seg in segments:
            if entity_lower in seg["text"].lower():
                for w in seg["text"].lower().split():
                    clean = re.sub(r'[^a-z]', '', w)
                    if clean and len(clean) > 4 and clean not in _STOP_WORDS:
                        context_words.append(clean)
        entity_contexts[entity] = Counter(context_words).most_common(3)

    # Build natural sentences about the content
    if guest_name:
        # Find what the guest works on
        work_entities = [e for e in top_entities
                         if e.lower() != guest_name.lower()]
        if work_entities:
            parts.append(
                f"{guest_name} discusses their work with "
                f"{', '.join(work_entities[:3])}"
                f"{' and more' if len(work_entities) > 3 else ''}."
            )
    else:
        parts.append(
            f"The conversation covers {', '.join(top_entities[:3])}"
            f"{' and more' if len(top_entities) > 3 else ''}."
        )

    # Add a line about the broader themes if detectable
    all_context = []
    for entity, ctx in entity_contexts.items():
        all_context.extend([w for w, c in ctx])
    theme_freq = Counter(all_context)

    theme_mapping = {
        "agent": "the role of AI agents",
        "agents": "the role of AI agents",
        "gaming": "Web3 gaming",
        "crypto": "the crypto ecosystem",
        "social": "decentralized social platforms",
        "decentralized": "decentralized technology",
        "tournament": "competitive gaming",
        "community": "community building",
        "wallet": "wallet infrastructure",
    }
    themes = []
    for word, count in theme_freq.most_common(10):
        if word in theme_mapping and theme_mapping[word] not in themes:
            themes.append(theme_mapping[word])
            if len(themes) >= 2:
                break

    if themes:
        parts.append(
            f"The discussion explores {' and '.join(themes)}."
        )

    return " ".join(parts)


def generate_chapters(segments: list) -> str:
    """Generate YouTube chapter timestamps with descriptive titles.

    Uses entity-aware topic segmentation to find natural break points,
    then generates titles from the most distinctive content in each section.
    """
    if not segments:
        return "00:00 Introduction"

    total_duration = segments[-1]["end"]

    # Target chapters based on video length
    if total_duration < 300:
        target = 3
        min_spacing = 60
    elif total_duration < 900:
        target = 5
        min_spacing = 90
    elif total_duration < 1800:
        target = 7
        min_spacing = 120
    elif total_duration < 3600:
        target = 9
        min_spacing = 150
    else:
        target = 12
        min_spacing = 180

    # Get global entities for comparison
    global_entities = _extract_entities(segments)

    # Find topic boundaries
    boundary_scores = _segment_topics(segments, target)

    # Select boundaries with minimum spacing
    chapter_indices = [0]  # Always start at 0
    used_times = {0.0}

    for seg_idx, score in boundary_scores:
        if len(chapter_indices) >= target:
            break

        seg_time = segments[seg_idx]["start"]
        if seg_time < 10:
            continue

        too_close = any(abs(seg_time - t) < min_spacing for t in used_times)
        if too_close:
            continue

        # Skip if the segment at this boundary is just filler
        if _is_low_content(segments[seg_idx]["text"]):
            # Look at next few segments instead
            found = False
            for offset in range(1, 4):
                if seg_idx + offset < len(segments):
                    if not _is_low_content(segments[seg_idx + offset]["text"]):
                        seg_idx = seg_idx + offset
                        seg_time = segments[seg_idx]["start"]
                        found = True
                        break
            if not found:
                continue

        chapter_indices.append(seg_idx)
        used_times.add(seg_time)

    # If too few chapters, add evenly spaced ones
    if len(chapter_indices) < 3 and total_duration > 120:
        interval = total_duration / 4
        for n in range(1, 4):
            target_time = interval * n
            nearest_idx = min(
                range(len(segments)),
                key=lambda i: abs(segments[i]["start"] - target_time)
            )
            seg_time = segments[nearest_idx]["start"]
            too_close = any(abs(seg_time - t) < min_spacing / 2 for t in used_times)
            if not too_close and seg_time > 10:
                chapter_indices.append(nearest_idx)
                used_times.add(seg_time)

    # Sort by segment index
    chapter_indices = sorted(set(chapter_indices))

    # Generate titles for each chapter section
    chapters = []
    for i, start_idx in enumerate(chapter_indices):
        end_idx = chapter_indices[i + 1] if i + 1 < len(chapter_indices) else len(segments)
        time = segments[start_idx]["start"]

        if i == 0:
            # First chapter: try to detect show name or use "Introduction"
            show = _detect_show_name(segments)
            guest = _detect_guest(segments)
            if show and guest:
                title = f"{show} with {guest}"
            elif guest:
                title = f"Introduction / Welcome {guest}"
            else:
                title = "Introduction"
        else:
            title = _generate_section_title(
                segments, start_idx, end_idx, global_entities
            )

        if title:
            chapters.append({"time": time, "title": title})

    # Format
    lines = []
    for ch in chapters:
        ts = _format_timestamp(ch["time"])
        lines.append(f"{ts} {ch['title']}")

    return "\n".join(lines)


def generate_tags(segments: list, project_name: str) -> str:
    """Generate YouTube tags mixing entities, phrases, and keywords.

    Strategy:
    1. Project name as primary tag
    2. Proper nouns / named entities (brands, people, products)
    3. Multi-word phrases from TF-IDF
    4. Single high-TF-IDF keywords
    """
    entities = _extract_entities(segments)
    tfidf = _compute_tfidf(segments)

    # Start with project name
    tags = [project_name]
    seen = {project_name.lower()}

    # Add top entities (proper nouns, brand names, etc.)
    for entity, count in entities.most_common(10):
        if count >= 2 and entity.lower() not in seen:
            tags.append(entity)
            seen.add(entity.lower())
            if len(tags) >= 6:
                break

    # Add multi-word phrases (bigrams from non-stopwords)
    full_text = " ".join(s["text"] for s in segments).lower()
    words_clean = re.findall(r'\b[a-z]{4,}\b', full_text)
    words_clean = [w for w in words_clean if w not in _STOP_WORDS]

    bigrams = Counter()
    for i in range(len(words_clean) - 1):
        bigram = f"{words_clean[i]} {words_clean[i+1]}"
        bigrams[bigram] += 1

    # Filter bigrams: both words must be meaningful
    bigram_stop = _STOP_WORDS | {"without", "bunch", "having", "maybe",
                                  "every", "somebody", "already", "another"}
    for phrase, count in bigrams.most_common(15):
        words_in_phrase = phrase.split()
        if count >= 3 and phrase not in seen:
            # Skip if either word is a stop/filler word
            if any(w in bigram_stop for w in words_in_phrase):
                continue
            tags.append(phrase)
            seen.add(phrase)
            if len(tags) >= 12:
                break

    # Fill with TF-IDF keywords (skip generic/filler)
    tfidf_stop = {"exactly", "having", "people", "really", "pretty",
                  "already", "personally", "basically", "literally"}
    for word, score in tfidf:
        if word not in seen and len(word) > 4 and word not in tfidf_stop:
            tags.append(word)
            seen.add(word)
            if len(tags) >= 20:
                break

    # Detect guest name and add as tag
    guest = _detect_guest(segments)
    if guest and guest.lower() not in seen:
        tags.insert(1, guest)  # Right after project name

    return ", ".join(tags[:20])
