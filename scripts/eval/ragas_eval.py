import asyncio
import json

import httpx
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, faithfulness


async def run_eval():
    print("Starting evaluation...")
    async with httpx.AsyncClient() as client:
        # 1. Fetch 10 records
        try:
            records_resp = await client.get(
                "http://127.0.0.1:8000/api/v1/records?limit=10"
            )
            records_resp.raise_for_status()
            records = records_resp.json().get("records", [])
        except Exception as e:
            print(f"Failed to fetch records. Is the ingestor running? {e}")
            return

        if not records:
            print("No records found for evaluation.")
            return

        eval_data = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],  # optional for some metrics, but keeping empty or matching length
        }

        for record in records:
            record_id = record["id"]
            source = record.get("source")
            raw_data = record.get("raw_data", {})
            record_text = f"Source: {source}, Data: {json.dumps(raw_data)}"

            # 2. Analyze
            try:
                analyze_resp = await client.post(
                    f"http://127.0.0.1:8000/api/v1/records/{record_id}/analyze"
                )
                analyze_resp.raise_for_status()
                analysis = analyze_resp.json()
                answer = json.dumps(analysis)
            except Exception as e:
                print(f"Analysis failed for {record_id}: {e}")
                continue

            # 3. Context
            try:
                search_resp = await client.post(
                    "http://127.0.0.1:8001/search",
                    json={"query": record_text, "top_k": 3, "collection": "records"},
                )
                search_resp.raise_for_status()
                contexts = [
                    r.get("text", "") for r in search_resp.json().get("results", [])
                ]
            except Exception as e:
                print(f"Search failed for {record_id}: {e}")
                contexts = ["No context"]

            eval_data["question"].append(record_text)
            eval_data["answer"].append(answer)
            eval_data["contexts"].append(contexts)
            eval_data["ground_truth"].append("Not available")

        if not eval_data["question"]:
            print("No successful evaluations.")
            return

        print(f"Evaluating {len(eval_data['question'])} items...")
        dataset = Dataset.from_dict(eval_data)

        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy],
        )

        df = result.to_pandas()
        report = {
            "aggregate": result,  # ragas result object is dict-like
            "records": json.loads(df.to_json(orient="records")),
        }

        with open("scripts/eval/ragas_report.json", "w") as f:
            json.dump(report, f, indent=2)

        print("Evaluation complete. Report saved to scripts/eval/ragas_report.json")


if __name__ == "__main__":
    asyncio.run(run_eval())
