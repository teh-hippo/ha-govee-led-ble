"""H617A scene catalogue — unified registry of all scenes.

Generated from Govee API: app2.govee.com/appsku/v1/light-effect-libraries?sku=H617A
Confirmed working on real H617A hardware (2026-02-08).

To regenerate, run:
    curl -s "https://app2.govee.com/appsku/v1/light-effect-libraries?sku=H617A" \
        -H 'AppVersion: 9999999'
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneEntry:
    """A single scene definition."""

    name: str
    code: int
    param: str  # base64 scenceParam; empty for simple scenes
    category: str

    @property
    def is_simple(self) -> bool:
        """True if this scene uses a single-packet command."""
        return not self.param


# fmt: off
SCENES: dict[str, SceneEntry] = {
    "sunrise": SceneEntry("Sunrise", 0, "", "Natural"),
    "sunset": SceneEntry("Sunset", 1, "", "Natural"),
    "forest": SceneEntry("Forest", 2163, "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8FAgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC7hQBAP8AAAAAAAAAAA==", "Natural"),
    "aurora": SceneEntry("Aurora", 2164, "AiAAAAABAgH/MgEAAAAA+jIDAP8AAP//qv8AAwCAAAAAACMAAAADAgH/GQD6AAAC+gAEf/8A//8AoP//AP//FAH6AAD/AA==", "Natural"),
    "lightning": SceneEntry("Lightning", 2165, "ASmBAgEBAgH/AAH/AQEC/yMG////AAAA////AAAA////AAAAFQXMEQXNAA==", "Natural"),
    "starry sky": SceneEntry("Starry Sky", 2166, "AiAAAAACAAH/GQF4MjICyDIDAAD/AH7/AAD/AAAAAAAAACMAAg8DAAH/FAH6FBQC/TIEAAD/////AOz/AAD/AAAAAAAAAA==", "Natural"),
    "spring": SceneEntry("Spring", 2167, "AykAAgoFAgH/GQAAAAAC+jIG/zgA/38AAP8AAAAAAP//iwD/AACAAAAAACMAAh4KAAH//wAAAAAB+gAE8QAd/3UA/8AA/0sAAAD/AAH6AB0AAAABAAEyAAHIMjICyDICAP8A//8AAAAAAAAAAA==", "Natural"),
    "summer": SceneEntry("Summer", 2168, "AhoAAAABAgH//wAAAAAA/zIBM///AwCAAAAAACYAAh4KAAH//wAAAAAA+gAFAAD/AP///8AA//8AAAX/AAAAAAD/AA==", "Natural"),
    "fall": SceneEntry("Fall", 2169, "AhoAAAABAgH//wAAAAAA/zIB/zgAAwCAAAAAACkAAh4KAAH//wAAAAAA+gAG8QAd/3UA/8AA/0sA/wAAAAAAEADcAAD/AA==", "Natural"),
    "winter": SceneEntry("Winter", 2170, "AxoAAAABAgH/CgHIFAoA/TIB////AwCAAAAAACMAAh4KAAH/BQCgFBQB/QAE////t///pv//d///FAHIEQH9/yMAAh4KAAH/BQCgFBQB/QoE////t///pv//d///EQHIEgH8AA==", "Natural"),
    "rainbow": SceneEntry("Rainbow", 22, "", "Natural"),
    "fire": SceneEntry("Fire", 2171, "BR0AAAAWAAFwMgO7FBQC1RQC/1kH////AwD/EwD/ASknAAAFAgH/mQL/Xx4CAP8GAAAA/////20H/00H/w4H/wgJEgD8EACAAikhAAAGAgH/mQL/Xx4CAP8GAAAA/////20H/00H/w4H/wgJEAD+EAD9AilDAhQUAAH//wCAFBQB6hQG/xUH/wgJ/wgJ/ykH/wcTAAAAEwD8AACAAykkAAABAAH/AACAFBQB6RQG/xUH/zkH/44H/14H/wcT/w8HFwD5AAD/BA==", "Natural"),
    "wave": SceneEntry("Wave", 2172, "ASMAAAACAAH//wAAAAAC/TIEAAD/AH7/AOz/AAD/EwH8AAAAAA==", "Natural"),
    "deep sea": SceneEntry("Deep sea", 2173, "Ah0AAAABAAH//wAAAAAA3DICAGT/AAD/AAAAAAAAABoAAgoBAgH/KAHXAAAAADIBAP+WAAAAAAAAAA==", "Natural"),
    "karst cave": SceneEntry("Karst Cave", 2174, "AyYAAQAKAgH/GQFkCgoCyBQFvQD//0kA/5YAnv8AFP//FgFkAAAAACkAAh4PAgH/ZAHmAAAB+hQGBP8AAP8AiwD//0v/8QAe//8AAAAAAAAAACAAAAABAAGWMgDmFBQC+hQDAMz/AG7/AAP/AAAAAAAAAA==", "Natural"),
    "glacier": SceneEntry("Glacier", 2175, "BCBQAQAZAAH/AAD/MjICZAADAAD/AP//////FgD/AAAAACBVAQAZAAH/AAD/MjICZAADAAD/AP//////FAD/AAAAACkAAh4FAAH/AAL/MjIC/xQGAP//AAAA////AAAA////AP//AAAAEgD6ACYAAh4FAAH/AAL/MjIC3AIFAP//AAAA////AAAAAP//AAAAEgDrAA==", "Natural"),
    "gobi desert": SceneEntry("Gobi Desert", 2176, "AiCgAQAyAAGWlgAAAAAA3BQDljIAyDwA0jIAAAAAAAAAAB0AAgUBAAH/FAHwFFAC+kYC/38A/7QAAAAAAAAAAA==", "Natural"),
    "moonlight": SceneEntry("Moonlight", 2177, "AiBgAgoFAgFkZABkAAAC/RQD//8A//+g////AAAAEAXcAB2gAQAyAAFkHgAAAAAA/RQCAABQAB6gAAAAAAAAAA==", "Natural"),
    "flower field": SceneEntry("Flower Field", 2178, "AiygAh4ZAgH/lgDSAAAC/gAH0QBe/wMA/2wA//8A/38A/wAA9QD/AAAAEADwABqgAQAyAAEyFAAAAAAA+hQBzwBiAAAAAAAAAA==", "Natural"),
    "downpour": SceneEntry("Downpour", 2179, "BCMwAgQBAAH/AAL/AgIA/2QE////AAAAAAAAAAAAAACAEQD0ACkUAgIBAAH/AAD/AQQA/yYGAAAAAAAA////AAAA////AAAAAACAEwDfAC9CAgUDAAL/AAL/AgH/AAD7KMgA/x4GAAAAAAAAAAAAAAAA////AAAAAACAAACAACAAAAAyAgIHAgGbgMgEAwOZfMAAgBQB////AACAAACAAA==", "Natural"),
    "sunny": SceneEntry("Sunny", 2180, "Ax0AAAABAAHxwwB/FBQAkgICAP//AAD/AAB/AAB/AR0AAhkBAAHxwwDKFBQAfxQC////AAAAAAB/EQD8AR0AAhkBAAHxwwDKFBQAfxQC////AAAAAAB/EwD8AQ==", "Natural"),
    "volcano": SceneEntry("Volcano", 2181, "BSNQAQAFAgH/CgD6AAACAAAE/wAAyAAAlgAAMgAAFgH5AAAAACNVAQAFAgH/CgD6AAACAAAE/wAAyAAAlgAAMgAAFAH6AAAAACNVAQAFAgH/CgD6AAACAAAE/wAAyAAAlgAAMgAAFAH6AAAAACNQAQAFAgH/CgD6AAACAAAE/wAAyAAAlgAAMgAAFgH5AAAAAB2gAgoFAgH/CgD/AAACAAACMgAA/wAAEADJAAAAAA==", "Natural"),
    "cornfield": SceneEntry("Cornfield", 2182, "Bh0wAQADAgH/AAD/FBQA5xQC/0EA/4IAEQDyAAAAAB0yAQADAgH/AAD/FBQA5hQC/0EA/2MAEQDyAAAAAB00AQADAgH/AAD/FBQA5hQC/0EA/2MAEQDyAAAAAB02AQADAgH/AAD/FBQA5xQC/0EA/5YAEQDyAAAAAB0oAQACAgH/AAD/FBQA5h4C/0EA/2MAEQDyAAAAABqgAQAyAAFkCgAAAAAA/zIBPCMAERTwAAAAAA==", "Natural"),
    "meteor shower": SceneEntry("Meteor shower", 2183, "AiA3AQAAAgH/qwIAAAABAAADAAD/AP//////AAD6EAH1ACAwAQADAgH/qwIAAAABAAADAAD/AP//////AAD6EAH5AA==", "Natural"),
    "flying": SceneEntry("Flying", 2184, "Ax0AAgYDAgG9YgPMCgoDxhQC/44H/wYVBADQAQD5BSMAAgUCAgHbWQPMCg8DzRQE7Tj+//sHSO3+Of5dBADQAQD5BSAAAAABAAHMzAK+CgoA7kYD/26Y/1MN/9gvAACAAACAAQ==", "Natural"),
    "tree shadow": SceneEntry("Tree shadow", 2185, "Ah0AAAABAAGnVQO+Dw+A6RQCdP5eUP4IAACAAACAACkAAgYBAAGPRgPLBQoA6RQG/+0w5/9jAAAAAAAA//8AAAAABQDjAAD7AA==", "Natural"),
    "cherry blossoms": SceneEntry("Cherry blossoms", 2186, "Ah0AAAABAAFwcACAFBQA3BQC/zft/wb+AACAAACAAB0AAgUBAAE9GgCAFBQBgBQC/2r39Iv+AACAEgD1AA==", "Natural"),
    "stream": SceneEntry("Stream", 2187, "Ax2RAAACAgGdgwAAFBQAABQCW/+1VSr/FAP4AACAABoQAAABAAG1tQAAFBQA/xQBLpT/AACAAACAABqRAAACAgH/TALRFBQAABQBeP7ZBAD9AADpAA==", "Natural"),
    "ripple": SceneEntry("Ripple", 2188, "BRoAAAABAAH/AACAFBQAgBQBAAD/AACAAACAABpQAAABAAH/AACAFBQAgBQBAP//FgD5AACAABpVAAABAAH/AACAFBQAgBQBAP//FAD5AACAABoyAAABAAHMzACAFBQAgBQBCP9wFgD5AACAARo1AAABAAHMzACAFBQAgBQBCP97FAD5AACAAQ==", "Natural"),
    "desert b": SceneEntry("Desert B", 10005, "AyYAAAAFAgHLMwPJFBQDABQF/x4H/zcH/1oH/zcH/x4HAACAAACAABpQAwECAAH/AACAFBQAgBQB/zIHFgD5AACAABpVAwECAAH/AACAFBQAgBQB/zEHFAD5AACAAA==", "Natural"),
    "sand grains": SceneEntry("Sand Grains", 10006, "Ah0AAwQEAAGgoAAAFBQDABQC/4Mw/4UjAACAEAH3ARoAAAABAAH/jAH5FBQDAAcB/2MaAACAAACAAA==", "Natural"),
    "christmas": SceneEntry("Christmas", 2189, "AykAAgoFAgH/GQAAAAAC+jIG/zgA/38AAP8AAAAAAP///wAAFAH6AAAAACMAAg8DAAH/GQHmMjIB+jIE8QAdAP8AAP//////FgH6EgHcACAAAAABAgH/AAD+FBQA/xQD/wAAAAAAAP8AEQCAAAAAAA==", "Festival"),
    "halloween": SceneEntry("Halloween", 1173, "gwb/9QAFAP///wUA/+n/BQD///8FAP/p2QUA//j/BgAE/x4A/1oA/zIA/3gA", "Festival"),
    "candlelight": SceneEntry("Candlelight", 9, "", "Festival"),
    "birthday": SceneEntry("Birthday", 2190, "Ai8AAgoFAgL/GQAAAAD/GQAAAAAC+jIG/zgA/38AAP8AAAAAAP//iwD/AACAAAAAACMAAh4KAAH//wAAAAAB+gAE8QAd/3UA/8AA/0sAAAD/AAH6AA==", "Festival"),
    "fireworks": SceneEntry("Fireworks", 2191, "BCNQAQAZAAH/AAD/MjICZAAE/wAAAAD/AP//////FAD/AAAAACNVAQAZAAH/AAD/MjICZAAE/wAAAAD/AP//////FgD/AAAAACkAAg8FAAH/AAL/MjIC/wIG/wAAAAAA//8AAAAAAAD/AP//AAAAEgH6ACkAAg8FAAH/AAL/MjIC/wIGiwD/AAAA//8AAAAA/3L/AP//AAAAEgH6AA==", "Festival"),
    "party": SceneEntry("Party", 2192, "AzgAAh4KAgH/GQEUAAAC/xQL/wAAAP//AAD/////AAD//wAAiwD/AAAA////AP8AiwD/AAD/AAAAACwAAh4PAgH/GQMAMjIC+gAH/wAAAP//AAD/////AAD//wAAiwD/FADIAAAAACAAAAABAAEyMgAAMjIC/woD/xP//38AAAD/EQCAAAAAAA==", "Festival"),
    "dance party": SceneEntry("Dance Party", 2193, "AiwAAh4PAgH/GQEUAAAC+gAH/wAAAP//AAD/////AAD//wAAiwD/AAD/AAAAACwAAh4PAgH/GQMAMjIC+gAH/wAAAP//AAD/////AAD//wAAiwD/AAAAAAAAAA==", "Festival"),
    "mother's day": SceneEntry("Mother's Day", 2194, "AiAAAAABAAH//wEAAAAA3DID/wsA6QD/zAD/AAAAAAAAACAAAigBAgH/KAHXIBQAADID/3///z8A////AAAAAAAAAA==", "Festival"),
    "father's day": SceneEntry("Father's Day", 2195, "Ah0AAAABAAH//wEAAAAA3DICAAD/AP//AAAAAAAAABoAAigBAgH/KAHXIBQAADIB////AAAAAAAAAA==", "Festival"),
    "white light": SceneEntry("White Light", 10565, "ARoAAAABAAH//wAAFBQAABQB/5Y+AACAAACAAA==", "Life"),
    "sweet": SceneEntry("Sweet", 1170, "gwH/tP8yAATwAB7qACu8AP/jAP8=", "Life"),
    "romantic": SceneEntry("Romantic", 7, "", "Life"),
    "movie": SceneEntry("Movie", 4, "", "Life"),
    "siren": SceneEntry("Siren", 2196, "Ah0AAAAKAAH//wAAAAAC/xQC/wAAAAD/EADIAAAAACMAAhQKAAH//wAAAAAA/woE////AP//AAD/////EQD+AAAAAA==", "Life"),
    "night": SceneEntry("Night", 2197, "Ah0AAAAFAAGWBQGWMjIC3DICAAD/nADIAAAAAAAAACAAAAADAgGWBQHXMjICADIDiwD/AAAAAAD/AAAAAAAAAA==", "Life"),
    "sleep": SceneEntry("Sleep", 2198, "ASAAAAAFAAFMMwGWMjIC3DID/38A/0EA/7AAAAAAAAAAAA==", "Life"),
    "morning": SceneEntry("Morning", 2199, "Ah0AAAABAAHIMgFkMjIAyDIC////AP//AAAAAAAAABoAAgoBAgH/KAG0MjIAADIBAP+WAAAAAAAAAA==", "Life"),
    "afternoon": SceneEntry("Afternoon", 2200, "Ah0AAAABAAH//wAAAAAA3DIC////AP//AAAAAAAAAB0AAgoBAgH/KAHXAAAA+jICAMX/////AAAAAAAAAA==", "Life"),
    "work": SceneEntry("Work", 2201, "AR0AAAABAgH//wAAAAAA+pYC////j///AAAAAAAAAA==", "Life"),
    "leisure": SceneEntry("Leisure", 2202, "AiAAAAABAgH/MgAAAAAA9TID/wAA/2wA/38AAwCAAAAAAB2gAAAFAgH/MgD/FBQA8DIC/1AA7AAmAwCAEQD8AA==", "Life"),
    "meditation": SceneEntry("Meditation", 2203, "AiMAAAABAgHnNQAAAAAAblMEKwf/Bhz+Bkb+B3v/AwAcAAAAAB0AAQAKAgH/MgAAMgAA+jICAAB4AABQAwCAAAAAAA==", "Life"),
    "colorful": SceneEntry("Colorful", 2204, "ASYAAgoFAAH//wCeAAAB9QAF8QAd/3UA/8AA/0sA/1h7AAD/AAH6Aw==", "Life"),
    "candy": SceneEntry("Candy", 2205, "ASMAAAAKAAH//wAAFBQCABQE/0pV/1UhpP5eVvv+AACAAACAAA==", "Life"),
    "dreamlike": SceneEntry("Dreamlike", 2206, "AiMAAAAEAgH/UACAFBQDtgoEElP+iwD/MU7/iwD/AAD6AACAACAAAggBAAH//wM9CgoA/gED////AP//Nsn+AADuAACAAA==", "Life"),
    "dreamland": SceneEntry("Dreamland", 2207, "BRoAAQACAAH//wCAFBQB/xQB2gf/FQD9AACAARoAAQACAAH//wCAFBQB/xQB/7cHFQH9AACAARoAAQACAAH//wCAFBQB/xQB/zkHEQL6AwCAARoAAQACAAH//wCAFBQB/xQB/wbZFQD6AACAAR0AAAAKAAH//wCAFBQAwxQC/0AH/weNBQT3AACAAA==", "Emotion"),
    "energetic": SceneEntry("Energetic", 16, "", "Emotion"),
    "profound": SceneEntry("Profound", 2208, "AiMAAAAKAgH/CgIAAAACAAAEAAD/AHr/AMf/AP//EAH6AAAAACMAAAAKAgH/CgIAAAACAAAEAAD/AHH/ALL/AP//EgH6AAAAAA==", "Emotion"),
    "quiet": SceneEntry("Quiet", 2209, "ASAAAAAIAgH/MgHIMhQC+jIDbv8A1f8A1f8AEQKAAAAAAA==", "Emotion"),
    "warm": SceneEntry("Warm", 2210, "AyNQAQAPAgH/CgIAAAACAAAE/wAA/1oA/3gA5QA2EAD6AAAAACMAAQAPAgH/CgIAAAACAAAE/wAA/1oA/3gA8gAcEAD6AAAAABoAAAABAgGWMgAAAAAA+jIB/4H/EQCAAAAAAA==", "Emotion"),
    "flow": SceneEntry("Flow", 2211, "ASkAAQAyAgH/MgD/MhkB/AAGAP//AKP/AHT/AAAAAAAAAAAAAAAAAAAAAA==", "Emotion"),
    "longing": SceneEntry("Longing", 2212, "AiMAAAACAgH/MgHIMlAB0zIEAAD/AHr/swCb/zP/AAAAAAAAACMAAg8FAgH/CgPIMjIByDIEjAD/AHH/iwD//0n/FAGWAAAAAA==", "Emotion"),
    "happy": SceneEntry("Happy", 2213, "BSkAAAAIAAH/AAP/ZGQCADIG/wAA/38A//8AAP//AAD/AP8AEgD8AAAAAhoRAAABAgH/AAAAAAAA/zIBiwD/AAAAEgH8ARoTAAABAgH/AAAAAAAA/zIBAAD/AAAAEgH8ARoVAAABAgH/AAAAAAAA/zIBAP8AAAAAEgH9ARoVAAABAgH/AAAAAAAA/zIBAP//AAAAEgH8AQ==", "Emotion"),
    "mysterious": SceneEntry("Mysterious", 2214, "AikAAAABAAH/AAH/ZGQA/AMG/wAAAP8AAAD//38A//8AiwD/AAAAAAAAAikAAAAIAAH/AAP/ZGQCADIG/3D//38A//8AAP//AKD/AP8AEgD8AAAAAg==", "Emotion"),
    "release": SceneEntry("Release", 2215, "AiZQAQAFAAH/AAAAZAoCyBQFAAD/AP//AP8A//8A/38AFgD9AAAAACZVAQAFAAH/AAAAZAoCyBQFAAD/AP//AP8A//8A/38AFAD8AAAAAA==", "Emotion"),
    "game": SceneEntry("Game", 2216, "AiYAAAAFAAH//wAAAAAC/zIFiwD/AAD//xP//38A/wAAEwH9AAAAACYAAAADAAH//wAAAAAC/zIFiwD/AAD/AAAA////AP//EwH8AAAAAA==", "Emotion"),
    "disco": SceneEntry("Disco", 2217, "AiwAAgoFAgH//wAAAAAB/wAH/wAAAP//AAD/////AAD//wAAiwD/AAD/EAH4ACkAAgoDAgH/CgAZAAAC/zIGiwD/AAD/AAAA////AAAA/wAAAwCAEgH6AA==", "Emotion"),
    "optimistic": SceneEntry("Optimistic", 2218, "ASAAAQAKAAHl5QAAFBQBAAED/2iN//JuGP6DAACAAACAAA==", "Emotion"),
    "heartbeat": SceneEntry("Heartbeat", 2219, "Ah0AAAACAgH/AAEAFBQCABQC/wf7B/P/AACAAACAAB0AAAABAgH/BAOAFBQA/AUC/wAAAAAAAACAAACAAQ==", "Emotion"),
    "cheerful": SceneEntry("Cheerful", 2220, "Ax1QAQAFAAH//wGAFBQBgBQC/38A/wAAFQD6AACAAR1VAQAFAAH//wGAFBQBgBQC/38A/wAAFwD6AACAASAAAAADAAFtbQD5FBQCABQD//8A/4Un//8AAgD4AACAAA==", "Emotion"),
    "swing": SceneEntry("Swing", 2222, "BSMgAQACAgH/AAD/FBQA/xQE/0EA/4IA1ABX/5YAEQD8AAAAACMiAQACAgH/AAD/FBQA/xQE/0EA/2MA4wA5/7kAEQD6AAAAACMkAQACAgH/AAD/FBQA/xQE/0EA/2MA3gBE/7AAEQD7AAAAACMmAQACAgH/AAD/FBQA/xQE/0EA/5YA1QBV/64AEQD6AAAAACMoAQACAgH/AAD/FBQA/xQE/0EA/5YA7QAk/7IAEQD6AAAAAA==", "Funny"),
    "flash": SceneEntry("Flash", 2223, "ASagAQAIAAH//wAAAAAA/hQF//8A/38A/0UA/wAA2wBIFAH9AAAAAA==", "Funny"),
    "fight": SceneEntry("Fight", 2224, "BSMgAQACAgH//wD/FBQB/wYE/wAAAP////8AAP8AFAD5AACAACMkAQACAgH//wD/FBQB/wYE/wAAAP8A//8AAP//FgD6AACAACMiAQACAgH//wD/FBQB/wYE/wAAAP8A//8AAP//FAD7AACAACMmAQACAgH//wD/FBQB/wYE/wAAAP8A//8AAP//FgD7AACAACMoAQACAgH//wD/FBQB/wYE/wAAAP8A//8AAP//EAD5AACAAA==", "Funny"),
    "stacking": SceneEntry("Stacking", 2225, "AiAAAAABAAH//wAAAAAAyDID/wAAAP8AAAD/FADOAAAAACAAAQABAAH//wAAAAAAyDID/wAAAP8AAAD/EgD/AAAAAA==", "Funny"),
    "twinkle": SceneEntry("Twinkle", 8, "", "Funny"),
    "breathe": SceneEntry("Breathe", 10, "", "Funny"),
    "spin": SceneEntry("Spin", 2226, "BSYgAAABAgH/fgOACgoA8xQF/4wH//4HYf4IB/6uB7r+FQD4AACAACkiAAABAgH/GAOACgoA8xQG/4wH//4H/14H/wY9/wbTtAb+FwD4AACAACkkAAABAgH/GQOACgoA8hQG/4wH//4HCP+qBtr+CH3+1wb/FQD4AACAACkmAAABAgH/GQOACgoA8xQG/4wH//4H/waF9Qf/Vmb/B6L/FwD4AACAACkoAAABAgH/GQOACgoA8xQG/4wH//4H8VD/B2n/CP+RCP8PFQD4AACAAA==", "Funny"),
    "rhythm": SceneEntry("Rhythm", 2227, "AykkAAABAAH/AACAFBQAgAEG/wAAAAD///8AAP8AiwD//38AAACAAACAAClAAgQBAAH/AACAFBQB5gQG/wYbBwf///8AAP8A/38AAP//EgDyAADZASlGAgQBAAH/AACAFBQB5gQG/wAAAAD///8AAP8A/38AAP//EADzAACAAQ==", "Funny"),
    "bloom": SceneEntry("Bloom", 2228, "BCkwAAABAAH//wCAFBQB8hQG/wAA/38AcP6aB3H/9Rf///8AFgD5AACAACkjAAABAAH//wCAFBQB8hQG/wAA/38AcP6aByz//hH+//8AFAD6AACAACklAAABAAH//wCAFBQB8hQG/wAA/38AcP6aB1z//wf3//8AFgD6AACAACk3AAABAAH//wCAFBQB8hQG/wAA/38AcP6aB1n/8wf///8AFAD6AACAAA==", "Funny"),
}
# fmt: on


def get_scene_names() -> list[str]:
    """Return sorted list of all scene names."""
    return sorted(SCENES.keys())
