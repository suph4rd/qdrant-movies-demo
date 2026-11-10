# Local evaluation results

Recorded: 2026-11-09T12:58:58.297149+00:00. Host: macOS-26.5-arm64-arm-64bit-Mach-O; Python 3.15.2.

Protocol and frozen judgments: [README](README.md), [queries](data/queries.json).
Full measurements and model identity: [results.json](results/results.json).

Mean Recall@5: **0.830** (EN 0.840, RU 0.820).

These are 20 hand-selected queries with ten paired plot intents, not independent
samples or a broad benchmark. Many closely paraphrase the short catalog descriptions.
They verify retrieval behavior and do not establish a guaranteed quality improvement.

| Query | Relevant IDs | Top 5 IDs | Recall@5 |
| --- | --- | --- | --- |
| 01-en | [1] | [1, 95, 48, 192, 9] | 1.00 |
| 01-ru | [1] | [1, 149, 58, 9, 85] | 1.00 |
| 02-en | [4] | [4, 47, 36, 49, 27] | 1.00 |
| 02-ru | [4] | [4, 36, 27, 49, 191] | 1.00 |
| 03-en | [16, 55] | [16, 218, 177, 49, 137] | 0.50 |
| 03-ru | [16, 55] | [16, 90, 218, 184, 211] | 0.50 |
| 04-en | [21, 23, 101, 144] | [21, 95, 112, 113, 144] | 0.50 |
| 04-ru | [21, 23, 101, 144] | [21, 144, 95, 189, 112] | 0.50 |
| 05-en | [25, 157, 158, 159, 160] | [25, 198, 119, 160, 69] | 0.40 |
| 05-ru | [25, 157, 158, 159, 160] | [25, 238, 198, 69, 119] | 0.20 |
| 06-en | [86, 87] | [86, 87, 211, 85, 93] | 1.00 |
| 06-ru | [86, 87] | [86, 211, 87, 103, 191] | 1.00 |
| 07-en | [119] | [119, 15, 228, 218, 84] | 1.00 |
| 07-ru | [119] | [119, 218, 228, 84, 213] | 1.00 |
| 08-en | [174] | [174, 49, 32, 186, 180] | 1.00 |
| 08-ru | [174] | [174, 181, 180, 151, 137] | 1.00 |
| 09-en | [219] | [219, 109, 19, 178, 218] | 1.00 |
| 09-ru | [219] | [219, 178, 19, 186, 109] | 1.00 |
| 10-en | [243] | [243, 108, 247, 109, 249] | 1.00 |
| 10-ru | [243] | [243, 108, 109, 247, 127] | 1.00 |

First description request: 143.4 ms. Subsequent 19: min 18.2, median 25.5, p95 51.3 ms.
The server was already ready and had served earlier verification requests.
First means first in this evaluation client, not a cold model.
Timings include /info compatibility checks, TEI and Qdrant; they exclude HTML rendering.

## Recommendation comparison

| Source | Legacy top 5 | Semantic top 5 | Overlap@5 |
| --- | --- | --- | --- |
| The Matrix | Minority Report, The Terminator, Inception, RoboCop, Terminator 2: Judgment Day | The Martian, Avatar, Moon, Blade Runner, Ex Machina | 0.0 |
| The Martian | Men in Black, Ivan Vasilievich Changes His Profession, Back to the Future, Guardians of the Galaxy, Contact | Gravity, Interstellar, Moon, Arrival, The Matrix | 0.0 |
| Groundhog Day | About Time, Amélie, Yes Man, Singin' in the Rain, When Harry Met Sally... | The Hangover, Roman Holiday, Love and Doves, The Truman Show, About Time | 0.2 |
| Se7en | The Silence of the Lambs, No Country for Old Men, Come and See, Prisoners, Shutter Island | Memories of Murder, The Sixth Sense, The Silence of the Lambs, The Departed, Heat | 0.2 |
| The Lord of the Rings: The Fellowship of the Ring | Harry Potter and the Deathly Hallows: Part 2, The Lord of the Rings: The Two Towers, The Lord of the Rings: The Return of the King, Harry Potter and the Order of the Phoenix, Wonder Woman | The Lord of the Rings: The Two Towers, The Lord of the Rings: The Return of the King, The Hobbit: An Unexpected Journey, Harry Potter and the Deathly Hallows: Part 2, Harry Potter and the Order of the Phoenix | 0.8 |
| The Godfather | The Godfather Part II, Once Upon a Time in America, Casino, Raging Bull, Scarface | The Godfather Part II, Goodfellas, Prisoners, Parasite, Brother | 0.2 |
| Whiplash | Schindler's List, The Pianist, To Kill a Mockingbird, Murder on the Orient Express, Rashomon | A Beautiful Mind, Dead Poets Society, The Pianist, Fight Club, One Flew Over the Cuckoo's Nest | 0.2 |
| Titanic | The Handmaiden, Vertigo, Once Upon a Time in America, The Cranes Are Flying, In the Mood for Love | The Notebook, The Cranes Are Flying, Life of Pi, Love and Doves, In the Mood for Love | 0.4 |
| Ratatouille | Klaus, Madagascar, Ice Age, Finding Nemo, Up | Toy Story, Amélie, Office Romance, Shrek, The Iron Giant | 0.0 |
| The Shining | The Exorcist, The Conjuring, Pan's Labyrinth, The Others, It | The Others, The Conjuring, A Quiet Place, Parasite, Psycho | 0.4 |

## Limitations and weak cases

- 03-en: missing [55] at rank 5 for “Someone keeps living the same day.”.
- 03-ru: missing [55] at rank 5 for “Человек снова и снова проживает один день.”.
- 04-en: missing [23, 101] at rank 5 for “Detectives investigate a serial killer.”.
- 04-ru: missing [23, 101] at rank 5 for “Детективы расследуют серийные убийства.”.
- 05-en: missing [157, 158, 159] at rank 5 for “A boy attends a school for wizards.”.
- 05-ru: missing [157, 158, 159, 160] at rank 5 for “Мальчик учится в школе волшебников.”.

Recommendation overlap measures change, not preference quality. Inspect the lists:
semantic similarity can emphasize plot objects or franchise titles rather than mood.
The descriptions are one sentence long; missing details cannot reliably be recovered.
There is no personalization, reranker, hybrid retrieval, or training in this version.
