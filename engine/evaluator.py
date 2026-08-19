"""Tier-2 Cognitive Valuation Engine using Google AI Studio Gemini API with Context Caching and Fallback."""

import os
import re
import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import json_repair

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger("FacebookSnoof.Evaluator")


class DealEvaluationSchema(BaseModel):
    """Structured Pydantic schema for Gemini valuation JSON output."""
    is_valid_pc_hardware: bool = Field(description="True if post is selling legitimate PC hardware component or Full PC set.")
    hardware_name: str = Field(default="Unknown", description="Normalized name of hardware component or Full PC build.")
    item_category: str = Field(default="Other", description="Category: GPU, CPU, RAM, Motherboard, PSU, Storage, Full PC, Other.")
    asking_price: int = Field(default=0, description="Asking price extracted from post in Indonesian Rupiah (IDR).")
    estimated_market_price: int = Field(default=0, description="Estimated fair market secondhand price in IDR based on lookup table.")
    condition: str = Field(default="Unknown", description="Summary of item condition, defects, or accessories.")
    risk_flags: List[str] = Field(default_factory=list, description="Risk flags detected e.g. ex-mining, no box, defect, suspicious price.")
    deal_score: int = Field(default=0, ge=0, le=100, description="Deal score from 0 to 100 based on price gap and risk level.")
    verdict: str = Field(default="INVALID", description="Verdict label: GREAT_DEAL, GOOD_DEAL, FAIR_DEAL, OVERPRICED, RISKY, INVALID.")
    reasoning: str = Field(default="", description="One concise sentence explaining why this deal is good or why it is skipped.")


class SinglePostEvaluation(DealEvaluationSchema):
    """Structured Pydantic schema for single post evaluation in batch mode, including post_id."""
    post_id: str = Field(default="", description="Exact ID of the post being evaluated.")


class BatchEvaluationResponse(BaseModel):
    """Structured Pydantic schema for batch valuation JSON output containing evaluations for multiple posts."""
    evaluations: List[SinglePostEvaluation] = Field(default_factory=list, description="List of evaluations for each input post.")


class DealEvaluator:
    """Evaluates candidate Facebook Marketplace listings using Google AI Studio Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        primary_model: str = "gemini-2.5-flash-lite",
        fallback_model: str = "gemini-2.0-flash",
        timeout_seconds: int = 30,
        lookup_table_path: str = "lookup_table.md"
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if self.api_key == "YOUR_GEMINI_API_KEY":
            self.api_key = os.environ.get("GEMINI_API_KEY")

        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout_seconds
        self.lookup_table_path = lookup_table_path
        self.lookup_context = self._load_lookup_table()
        
        self.client = None
        if genai and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Initialized Google AI Studio Gemini Client successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI Client: {e}")
        elif not genai:
            logger.error("`google-genai` SDK is not installed. Please run `pip install google-genai`.")

    def _load_lookup_table(self) -> str:
        """Load reference market price lookup table from markdown file."""
        if os.path.exists(self.lookup_table_path):
            try:
                with open(self.lookup_table_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    logger.info(f"Loaded market price lookup table from: {self.lookup_table_path}")
                    return content
            except Exception as e:
                logger.error(f"Failed to read lookup table file: {e}")
        else:
            logger.warning(f"Lookup table file not found at: {self.lookup_table_path}")
        return "No lookup table reference available."

    def build_system_instruction(self) -> str:
        """Construct static system instruction with Indonesian market glossary, Full PC criteria, and lookup table for context caching."""
        return f"""You are an expert PC hardware appraiser in Indonesia. Analyze Facebook marketplace posts selling computer components or Full PC Desktop sets.

CRITICAL TRUTHFULNESS DIRECTIVE (ZERO HALLUCINATION):
- Extract ONLY what is EXPLICITLY stated in the input post text.
- NEVER invent, hallucinate, or guess hardware component names, specifications, or prices that are not mentioned in the post.
- DO NOT default to example hardware names if the post does not explicitly mention them!
- If the post text is vague, lacks specific hardware model details, or is selling non-PC items (laptops without specs, accessories, or general chatter), set "is_valid_pc_hardware": false and state the missing info in "reasoning".
- Always preserve the exact `post_id` provided for each post when outputting JSON responses.

Item Categories Supported:
- "GPU", "CPU", "RAM", "Motherboard", "PSU", "Storage", "Full PC" (PC Rakitan Full Set / Desktop Package), "Other".

Market Glossary (Indonesia):
- "full pc" / "pc rakitan" / "pc set": Complete desktop computer package.
- "batangan": Unit only (no box/accessories) -> reduce value by 5-10%.
- "minus": Has defect/damage -> heavily penalize score.
- "no display": Non-functional/broken -> score = 0.
- "ex-mining" / "ex-tambang": Crypto mining unit -> reduce value by 15-20%.
- "bu / butuh uang": Urgent sale -> higher probability of underpriced deal.
- "k" / "rb": Thousands (e.g., 500k = 500000), "jt": Millions (e.g., 1.5jt = 1500000).

REFERENCE MARKET LOOKUP TABLE:
\"\"\"
{self.lookup_context}
\"\"\"

Analyze the input post(s) and output a JSON response matching the required schema.
"""

    def parse_and_validate_response(self, raw_response: str) -> Optional[DealEvaluationSchema]:
        """Parse raw Gemini output using json_repair and validate via Pydantic DealEvaluationSchema."""
        try:
            target_str = raw_response.strip()
            
            # Extract JSON block {...} if embedded within markdown or prose
            json_match = re.search(r"\{.*\}", target_str, re.DOTALL)
            if json_match:
                target_str = json_match.group(0)

            if json_repair is not None:
                repaired_json = json_repair.repair_json(target_str)
            else:
                repaired_json = target_str
            
            if not repaired_json:
                logger.error("Parsed JSON string is empty.")
                return None

            data_dict = json.loads(repaired_json)
            if isinstance(data_dict, list) and len(data_dict) > 0:
                data_dict = data_dict[0]

            validated_schema = DealEvaluationSchema(**data_dict)
            return validated_schema
        except Exception as e:
            logger.error(f"Failed to parse or validate LLM JSON response: {e}\nRaw Output: {raw_response}")
            return None

    def parse_and_validate_batch_response(self, raw_response: str) -> List[SinglePostEvaluation]:
        """Parse raw Gemini batch output and validate as BatchEvaluationResponse or List of SinglePostEvaluation."""
        try:
            target_str = raw_response.strip()
            
            if json_repair is not None:
                repaired_json = json_repair.repair_json(target_str)
            else:
                repaired_json = target_str

            if not repaired_json:
                logger.error("Parsed JSON string is empty.")
                return []

            data = json.loads(repaired_json)
            evals = []

            if isinstance(data, dict):
                if "evaluations" in data and isinstance(data["evaluations"], list):
                    for item in data["evaluations"]:
                        try:
                            evals.append(SinglePostEvaluation(**item))
                        except Exception as e:
                            logger.warning(f"Failed to validate item in batch 'evaluations': {e}")
                else:
                    try:
                        evals.append(SinglePostEvaluation(**data))
                    except Exception as e:
                        logger.warning(f"Failed to validate dict item: {e}")
            elif isinstance(data, list):
                for item in data:
                    try:
                        evals.append(SinglePostEvaluation(**item))
                    except Exception as e:
                        logger.warning(f"Failed to validate item in batch list: {e}")

            return evals
        except Exception as e:
            logger.error(f"Failed to parse or validate batch LLM JSON response: {e}\nRaw Output: {raw_response}")
            return []

    def evaluate_post(self, post_text: str) -> Optional[DealEvaluationSchema]:
        """Evaluate raw Facebook post text using Gemini API with primary model and automatic fallback model."""
        if not post_text or len(post_text.strip()) < 10:
            return None

        if not self.client:
            logger.error("Gemini API Client is not initialized. Please configure `api_key` in config.yaml or set `GEMINI_API_KEY` env var.")
            return None

        system_instruction = self.build_system_instruction()
        user_prompt = f"INPUT POST:\n\"\"\"{post_text}\"\"\""

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=DealEvaluationSchema,
            temperature=0.1,
            top_p=0.95
        )

        models_to_try = [self.primary_model, self.fallback_model]
        if self.primary_model == self.fallback_model:
            models_to_try = [self.primary_model]

        for model_name in models_to_try:
            try:
                logger.info(f"Sending evaluation request to Gemini API ({model_name})...")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=config
                )
                
                raw_output = response.text
                logger.info(f"Gemini API ({model_name}) response received ({len(raw_output)} chars).")
                logger.debug(f"RAW GEMINI RESPONSE:\n{raw_output}")
                
                parsed_res = self.parse_and_validate_response(raw_output)
                if parsed_res:
                    return parsed_res

            except Exception as e:
                logger.warning(f"Gemini API request failed for model [{model_name}]: {e}")
                if model_name != models_to_try[-1]:
                    logger.info(f"Failing over to fallback model [{self.fallback_model}]...")
                    continue

        logger.error("All Gemini API models failed to evaluate post.")
        return None

    def evaluate_batch(
        self,
        candidate_posts: List[Dict[str, Any]],
        batch_size: int = 20
    ) -> Dict[str, SinglePostEvaluation]:
        """
        Evaluate candidate Facebook posts in chunks of `batch_size` using 1 API call per chunk.
        
        Args:
            candidate_posts: List of dicts, each containing at least 'post_id' and 'post_text'.
            batch_size: Max posts per Gemini API call (default 20).
            
        Returns:
            Dict mapping post_id -> SinglePostEvaluation
        """
        if not candidate_posts:
            return {}

        if not self.client:
            logger.error("Gemini API Client is not initialized. Cannot perform batch evaluation.")
            return {}

        results: Dict[str, SinglePostEvaluation] = {}
        
        # Split candidate_posts into chunks of batch_size
        chunks = [candidate_posts[i:i + batch_size] for i in range(0, len(candidate_posts), batch_size)]
        logger.info(f"Starting batch evaluation for {len(candidate_posts)} posts across {len(chunks)} chunk(s) (batch size: {batch_size})...")

        system_instruction = self.build_system_instruction()

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=BatchEvaluationResponse,
            temperature=0.1,
            top_p=0.95
        )

        for chunk_idx, chunk in enumerate(chunks, 1):
            logger.info(f"Processing evaluation batch chunk {chunk_idx}/{len(chunks)} ({len(chunk)} posts)...")
            
            formatted_posts = []
            for post in chunk:
                p_id = str(post.get("post_id", ""))
                p_text = post.get("post_text", "").strip()
                formatted_posts.append(f"--- POST START (ID: {p_id}) ---\n{p_text}\n--- POST END ---")
            
            user_prompt = "EVALUATE THE FOLLOWING LIST OF POSTS AND RETURN EVALUATIONS FOR EACH:\n\n" + "\n\n".join(formatted_posts)

            models_to_try = [self.primary_model, self.fallback_model]
            if self.primary_model == self.fallback_model:
                models_to_try = [self.primary_model]

            chunk_success = False
            for model_name in models_to_try:
                try:
                    logger.info(f"Sending batch request ({len(chunk)} posts) to Gemini API [{model_name}]...")
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=config
                    )
                    
                    raw_output = response.text
                    logger.info(f"Gemini API ({model_name}) batch response received ({len(raw_output)} chars).")
                    logger.debug(f"RAW BATCH RESPONSE:\n{raw_output}")
                    
                    parsed_evals = self.parse_and_validate_batch_response(raw_output)
                    if parsed_evals:
                        for single_eval in parsed_evals:
                            if single_eval.post_id:
                                results[single_eval.post_id] = single_eval
                        logger.info(f"Batch chunk {chunk_idx} successfully evaluated ({len(parsed_evals)} items parsed).")
                        chunk_success = True
                        break
                    else:
                        logger.warning(f"Batch response parsing yielded 0 valid evaluations using [{model_name}].")

                except Exception as e:
                    logger.warning(f"Gemini API batch request failed for model [{model_name}]: {e}")
                    if model_name != models_to_try[-1]:
                        logger.info(f"Failing over to fallback model [{self.fallback_model}] for batch chunk {chunk_idx}...")
                        continue

            # Emergency Fallback: If both models fail for this batch chunk, fallback to individual post evaluations
            if not chunk_success:
                logger.error(f"Batch chunk {chunk_idx} failed total across all models. Executing emergency individual evaluation fallback for {len(chunk)} posts...")
                for post in chunk:
                    p_id = str(post.get("post_id", ""))
                    p_text = post.get("post_text", "")
                    single_res = self.evaluate_post(p_text)
                    if single_res:
                        results[p_id] = SinglePostEvaluation(
                            post_id=p_id,
                            **single_res.model_dump()
                        )
                        logger.info(f"Individual fallback evaluation succeeded for post {p_id}.")
                    else:
                        logger.error(f"Individual fallback evaluation failed for post {p_id}.")

        return results

