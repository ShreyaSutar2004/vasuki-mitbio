"""VASUKI local Qwen chatbot (BLAST + Ramachandran assistant)."""

import os
import re
import sys
import threading
import pandas as pd

from .model_manager import load_model


# ============================================================
# SYSTEM PROMPTS
# All AI instructions are maintained in this file.
# ============================================================

GENERAL_SYSTEM_PROMPT = """
You are VASUKI, a scientific assistant integrated into a
bioinformatics application for protein modelling and analysis.

You assist researchers with:
- Bioinformatics
- Protein sequence analysis
- Comparative modelling
- Protein structure validation
- Molecular biology
- Scientific data interpretation

SCIENTIFIC RELIABILITY RULES:

1. Provide scientifically accurate answers.
2. Never invent experimental results, statistics, residue
   identities, structures, references, or numerical values.
3. Clearly distinguish supplied observations from scientific
   interpretation and hypotheses.
4. If information is missing, explicitly say so.
5. Do not pretend to have executed a tool or inspected a file
   unless its contents were actually supplied.
6. Explain scientific concepts in accessible language.

RESPONSE STYLE:

Respond in plain text.

Use concise, point-by-point explanations when appropriate.

Do not use Markdown formatting.

Do not use # headings, asterisks, Markdown tables,
backticks, or decorative formatting.

Avoid unnecessary introductions and conclusions.

Prioritize clarity, accuracy, and useful information.
"""



BLAST_SYSTEM_PROMPT = """
You are VASUKI, a bioinformatics assistant inside a protein
homology-modelling application. You help a researcher choose and
understand BLAST templates.

You receive a ranked list of BLAST hits and a BEST TEMPLATE that the
application has already calculated (ranked by identity, then coverage,
then E-value, then score). Trust the ranking and the printed values.
Do not recalculate or reinterpret them.

HOW TO READ THE VALUES:
- Identity (%): higher is better. Above 40% is a reliable template,
  30-40% is usable with care, below 30% is risky.
- Coverage (%): how much of the query the hit covers. Higher is better.
- E-value: LOWER is better. 0.0 or a tiny value (for example 1e-50)
  means a highly significant match. Above 0.01 means a weak match.
- Score: higher is better.

RULES:
1. Use only the supplied hits. Never invent PDB IDs, chains, organisms
   or numbers. Quote values exactly as printed.
2. If asked which template to use, recommend the BEST TEMPLATE and
   justify it with its identity, coverage and E-value. Mention one
   alternative only if it is clearly close.
3. If the table cannot answer the question, say so in one line.
4. Sequence similarity suggests, but does not prove, the same fold
   or function.

ANSWER STYLE:
- Speak directly to the researcher, for example "Use 5HG1 chain A
  because ...". Never describe the user or the task, never write
  "The user is asking".
- Maximum 5 short lines. Plain text only. No markdown, headings,
  asterisks or tables.
- For a greeting or small talk, reply in one short sentence and do
  not analyse anything.
"""



RAMACHANDRAN_SYSTEM_PROMPT = """
You are VASUKI, a bioinformatics assistant inside a protein
homology-modelling application. You interpret Ramachandran
statistics for the researcher's model.

You receive one line per model with the residue count and the number
and percentage of residues in the Favoured, Allowed and Disallowed
regions. These numbers are the only data you have. You cannot see the
plot, the residue identities or the 3D structure.

HOW TO JUDGE THE STATISTICS (general guidelines):
- Favoured above 90%: good backbone quality. Above 95%: very good.
- Allowed: acceptable, usually flexible loops.
- Disallowed: ideally close to 0%. Under 1% is generally acceptable
  for a homology model but those residues should be checked. Above
  2% suggests refinement or loop remodelling is needed.
- Glycine is flexible and can sit in unusual regions. Proline is
  restricted. Outliers in loops or termini are less worrying than
  outliers in helices, strands or the active site.

RULES:
1. Quote the counts and percentages exactly as supplied, including
   the disallowed count. Never say there are no disallowed residues
   unless the data shows 0.
2. Never invent residue numbers, residue names, angles or values.
   If asked about a specific residue, say that residue-level data is
   not available.
3. Do not refuse to interpret the statistics because the plot or
   residue data is missing.
4. Give one practical suggestion only if the disallowed or allowed
   percentage justifies it (for example, check the outlier residues
   and refine those loops).

ANSWER STYLE:
- Speak directly to the researcher. Never describe the user or the
  task, never write "The user is asking".
- Maximum 5 short lines. Plain text only. No markdown, headings,
  asterisks or tables.
- For a greeting or small talk, reply in one short sentence and do
  not analyse anything.
"""


BREVITY_RULE = """
STRICT LENGTH RULE:
Answer ONLY what the user asked. Maximum 5 short lines.
Plain text only, no markdown, no headings, no asterisks.
For greetings or small talk, reply in one short sentence and do not
analyse anything.
Quote numbers exactly as they appear in the supplied data. Never
state a number that is not in the data.
"""


# ============================================================
# BLAST RESULT MANAGER
# ============================================================

class BlastManager:

    def __init__(self, df=None):
        self.df = None
        self.columns = {}

        if df is not None:
            self.set_data(df)

    def set_data(self, df):
        """Store BLAST results and identify relevant columns."""

        if df is None or df.empty:
            raise ValueError("The BLAST results table is empty.")

        self.df = df.copy()

        normalized = {
            str(col).strip().lower().replace(" ", "").replace("-", "_"): col
            for col in self.df.columns
        }

        aliases = {
            "evalue": ["e_value", "evalue", "expect", "e_value"],
            "identity": [
                "identity_%",
                "identity%",
                "percent_identity",
                "identity_percent",
                "pident"
            ],
            "coverage": [
                "coverage_%",
                "coverage%",
                "query_coverage",
                "qcovs",
                "qcovhsp"
            ],
            "score": ["score", "bitscore", "bit_score"],
        }

        for key, names in aliases.items():
            for name in names:
                normalized_name = name.strip().lower().replace(" ", "").replace("-", "_")

                if normalized_name in normalized:
                    self.columns[key] = normalized[normalized_name]
                    break

        # Convert available numeric columns to numeric values.
        for col in self.columns.values():
            self.df[col] = pd.to_numeric(
                self.df[col], errors="coerce"
            )

        return self.df

    def get_sorted(self, metric, ascending=True):
        """Return results sorted by a recognised BLAST metric."""

        if self.df is None:
            raise ValueError("No BLAST results have been loaded.")

        column = self.columns.get(metric)

        if column is None:
            raise ValueError(
                f"The BLAST table does not contain a usable {metric} column."
            )

        return self.df.sort_values(
            by=column,
            ascending=ascending,
            na_position="last"
        )

    def get_lowest_evalue(self):
        return self.get_sorted("evalue", ascending=True).head(1)

    def get_highest_identity(self):
        return self.get_sorted("identity", ascending=False).head(1)

    def get_highest_coverage(self):
        return self.get_sorted("coverage", ascending=False).head(1)

    def get_top_hits(self, count=10):
        return self.get_sorted("evalue", ascending=True).head(count)

    def _col(self, *keys):
        norm = {
            str(c).strip().lower().replace(" ", "").replace("-", "_"): c
            for c in self.df.columns
        }
        for key in keys:
            if key in norm:
                return norm[key]
        return None

    def ranked(self):
        """Rank by identity, coverage, E-value, then score."""
        by, asc = [], []
        for key, ascending in (
            ("identity", False),
            ("coverage", False),
            ("evalue", True),
            ("score", False),
        ):
            col = self.columns.get(key)
            if col is not None:
                by.append(col)
                asc.append(ascending)

        if not by:
            return self.df

        return self.df.sort_values(by=by, ascending=asc, na_position="last")

    @staticmethod
    def _num(value, fmt):
        try:
            if pd.isna(value):
                return "n/a"
            return format(float(value), fmt)
        except (TypeError, ValueError):
            return "n/a"

    def _hit_line(self, rank, row):
        pdb = self._col("pdb_id", "pdb", "pdbid")
        chain = self._col("chain")
        acc = self._col("accession")
        org = self._col("scientific_name", "organism", "species")

        parts = []

        if pdb is not None:
            label = f"PDB {row[pdb]}"
            if chain is not None:
                label += f" chain {row[chain]}"
            parts.append(label)
        elif acc is not None:
            parts.append(f"Accession {row[acc]}")

        if org is not None:
            parts.append(str(row[org]))

        ident = self.columns.get("identity")
        cov = self.columns.get("coverage")
        ev = self.columns.get("evalue")
        sc = self.columns.get("score")

        if ident is not None:
            parts.append(f"Identity {self._num(row[ident], '.1f')}%")
        if cov is not None:
            parts.append(f"Coverage {self._num(row[cov], '.1f')}%")
        if ev is not None:
            parts.append(f"E-value {self._num(row[ev], '.2e')}")
        if sc is not None:
            parts.append(f"Score {self._num(row[sc], '.1f')}")

        return f"{rank}. " + " | ".join(parts)

    def get_results_text(self, count=5):
        """Compact, labelled, ranked hit list for the language model."""

        if self.df is None:
            return "No BLAST results are available."

        if not self.columns:
            return self.df.head(count).to_string(index=False)

        top = self.ranked().head(count)

        return "\n".join(
            self._hit_line(i, row)
            for i, (_, row) in enumerate(top.iterrows(), start=1)
        )

    def get_best_text(self):
        if self.df is None or not self.columns:
            return "Not available."

        best = self.ranked().head(1)

        return self._hit_line(1, best.iloc[0])[3:]


# ============================================================
# CHATBOT
# ============================================================

class Chatbot:

    def __init__(self, token=None, blast_path=None):
        """
        token is retained for backward compatibility with older
        GUI code. Local Qwen does not require an API token.
        """

        self.blast_manager = None
        self.blast_path = blast_path

        self.llm = None
        self.ramachandran_text = ""

        # Warm up Qwen in the background so the first question does not
        # freeze the GUI while the model downloads / loads.
        threading.Thread(target=self._preload, daemon=True).start()

        # Separate conversation histories prevent one analysis
        # type from contaminating another.
        self.histories = {
            "general": [],
            "blast": [],
            "ramachandran": []
        }

        if blast_path and os.path.exists(blast_path):
            try:
                self.blast_manager = BlastManager(
                    pd.read_csv(blast_path, sep="\t")
                )
            except Exception as exc:
                print(f"Could not load BLAST results: {exc}")

    # --------------------------------------------------------
    # MODEL RESPONSE
    # --------------------------------------------------------

    def _preload(self):
        try:
            self.llm = load_model()
        except Exception as exc:
            print(f"VASUKI: Qwen preload failed: {exc}")

    @staticmethod
    def _clean(text):
        """Strip think-tags and markdown the model sneaks in."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
        text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*[*]\s+", "- ", text, flags=re.M)
        text = text.replace("**", "").replace("`", "")
        return text.strip()

    def _llm_response(
        self,
        prompt,
        system_prompt=None,
        task="general",
        max_tokens=250,
        question=None
    ):
        """Generate a response using the locally cached Qwen model."""

        if task not in self.histories:
            task = "general"

        if self.llm is None:
            self.llm = load_model()

        if system_prompt is None:
            system_prompt = GENERAL_SYSTEM_PROMPT + BREVITY_RULE

        messages = [{"role": "system", "content": system_prompt}]

        # Short history: last 2 turns of plain question/answer only
        # (never the big data prompts).
        messages.extend(self.histories[task][-4:])

        messages.append({"role": "user", "content": prompt})

        response = self.llm.create_chat_completion(
            messages=messages,
            temperature=0.1,
            repeat_penalty=1.05,
            max_tokens=max_tokens
        )

        answer = self._clean(
            response["choices"][0]["message"]["content"] or ""
        )

        if not answer:
            raise RuntimeError("Qwen returned an empty response.")

        self.histories[task].append(
            {"role": "user", "content": question or prompt}
        )
        self.histories[task].append(
            {"role": "assistant", "content": answer}
        )
        self.histories[task] = self.histories[task][-4:]

        return answer

    # --------------------------------------------------------
    # GENERAL BIOINFORMATICS
    # --------------------------------------------------------

    def generate_general_response(self, question):
        return self._llm_response(
            prompt=question,
            system_prompt=None,
            task="general"
        )

    # --------------------------------------------------------
    # BLAST QUERY DETECTION
    # --------------------------------------------------------

    def blast_query(self, question):
        keywords = [
            "blast",
            "alignment",
            "e-value",
            "evalue",
            "identity",
            "coverage",
            "query sequence",
            "subject sequence",
            "sequence similarity",
            "sequence identity",
            "best hit",
            "top hit",
            "template",
            "accession"
        ]

        question = question.lower()

        return any(keyword in question for keyword in keywords)

    # --------------------------------------------------------
    # BLAST INTERPRETATION
    # --------------------------------------------------------

    
    def generate_blast_response(self, user_msg):
        """Answer BLAST questions using actual BLAST result data."""

        if self.blast_manager is None:
            return self.generate_general_response(user_msg)

        hits = self.blast_manager.get_results_text(5)
        best = self.blast_manager.get_best_text()

        prompt = f"""BLAST HITS (top 5, best first):
{hits}

BEST TEMPLATE (calculated by the application):
{best}

USER MESSAGE:
{user_msg}

Answer in at most 5 short lines, plain text, speaking directly to the
researcher. If the message is a greeting, reply in one sentence."""

        return self._llm_response(
            prompt,
            system_prompt=BLAST_SYSTEM_PROMPT,
            task="blast",
            max_tokens=250,
            question=user_msg
        )


    # --------------------------------------------------------
    # RAMACHANDRAN INTERPRETATION
    # --------------------------------------------------------

    
    def generate_ramachandran_response(self, question, analysis_text=None):
        """
        Interpret Ramachandran analysis statistics.
        Accepts strings, tuples, lists, or other analysis outputs.
        """

        if analysis_text is None or not str(analysis_text).strip():
            analysis_text = self.ramachandran_text

        if isinstance(analysis_text, (tuple, list)):
            analysis_text = "\n".join(
                str(item)
                for item in analysis_text
                if item is not None
            )
        elif analysis_text is None:
            analysis_text = ""
        else:
            analysis_text = str(analysis_text)

        analysis_text = analysis_text.strip()

        if not analysis_text:
            return (
                "No Ramachandran analysis statistics are available. "
                "Please run the analysis before asking for interpretation."
            )

        prompt = f"""ANALYSIS RESULTS:
{analysis_text}

USER MESSAGE:
{question}

Answer in at most 5 short lines, plain text, speaking directly to the
researcher. If the message is a greeting, reply in one sentence."""

        return self._llm_response(
            prompt,
            system_prompt=RAMACHANDRAN_SYSTEM_PROMPT,
            task="ramachandran",
            max_tokens=250,
            question=question
        )


    # --------------------------------------------------------
    # MAIN RESPONSE ROUTER
    # --------------------------------------------------------

    def generate_response(self, user_msg):
        """
        Route questions to the appropriate context.

        If BLAST results are loaded, use the BLAST context for
        every question asked in the BLAST window.
        """

        if self.ramachandran_text:
            return self.generate_ramachandran_response(user_msg)

        if self.blast_manager is not None:
            return self.generate_blast_response(user_msg)

        return self.generate_general_response(user_msg)

    # --------------------------------------------------------
    # RESET CHAT
    # --------------------------------------------------------

    def reset_chat(self):
        for task in self.histories:
            self.histories[task] = []

    # --------------------------------------------------------
    # COMMAND-LINE ENTRY POINT
    # --------------------------------------------------------

def main():

    chatbot = Chatbot()

    print("VASUKI local Qwen chatbot")
    print("Type 'exit' to quit or 'reset' to clear conversation history.")

    while True:
        try:
            question = input("\nResearcher: ").strip()

            if question.lower() in ("exit", "quit"):
                break

            if question.lower() == "reset":
                chatbot.reset_chat()
                print("VASUKI: Conversation history cleared.")
                continue

            if not question:
                continue

            answer = chatbot.generate_response(question)
            print(f"\nVASUKI: {answer}")

        except KeyboardInterrupt:
            break

        except Exception as exc:
            print(f"\nVASUKI error: {exc}")


if __name__ == "__main__":
    main()