// Key additions to MossTTSApp.swift:

// 1. Update InferenceLine to parse config fields from status
// 2. Add tokenizer + config storage to InferenceManager  
// 3. Add tokenization logic for direct mode
// 4. Update SynthRequest.toPayload() to send input_ids/attention_mask for direct mode
// 5. Update synthesize endpoint
