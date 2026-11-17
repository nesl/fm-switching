// StudyORIN2-stack Part 2 — in-process warm-recall harness (libllama + libmtmd).
//
// Measures the Jetson Orin's REAL warm-recall latency on a path that does NOT
// re-send the image history on every question. The llama.cpp OpenAI server
// re-uploads and re-preprocesses every history image per call (StudyORIN1 Part 3
// found TTFT dominated by that, not model compute). Here we:
//   1. eval the frame history ONCE into the context KV (warm state),
//   2. for each question, rewind the KV to the history, eval ONLY the trailing
//      question tokens over the cached context, and decode the answer,
//   3. record first-token top-20 logprobs (for the equivalence gate vs the
//      server), TTFT, total latency, and the GPU clock.
//
// Same build as StudyORIN1-dense (llama.cpp c0fd786), same GGUF + mmproj, same
// context size (-c 57344), flash attention on, greedy (seed 0), one at a time.
//
// Token-identity with the server is by construction: the single user turn
// header + N images + question is chat-templated (jinja, the model's template)
// and tokenized with the same mtmd pipeline; the harness simply evaluates the
// [header+images] chunk prefix once and the [question+assistant] text suffix
// per question, so warm_tokens ++ suffix_tokens == the server's full prompt.

#include "llama.h"
#include "common.h"
#include "sampling.h"
#include "chat.h"
#include "mtmd.h"
#include "mtmd-helper.h"
#include "nlohmann/json.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>

using json = nlohmann::json;
using clk = std::chrono::steady_clock;
static double since(clk::time_point t0) {
    return std::chrono::duration<double>(clk::now() - t0).count();
}

static long read_gpu_freq(const std::string & path) {
    std::ifstream f(path);
    long v = -1;
    if (f) f >> v;
    return v;
}

// log-softmax top-k over a logits row
struct TopItem { std::string tok; float logprob; };
static std::vector<TopItem> topk_logprobs(const float * logits, int n_vocab,
                                          const llama_vocab * vocab, int k) {
    // logsumexp
    float mx = logits[0];
    for (int i = 1; i < n_vocab; i++) mx = std::max(mx, logits[i]);
    double se = 0.0;
    for (int i = 0; i < n_vocab; i++) se += std::exp((double)logits[i] - mx);
    double lse = mx + std::log(se);
    // partial top-k by logit (same order as logprob)
    std::vector<int> idx(n_vocab);
    for (int i = 0; i < n_vocab; i++) idx[i] = i;
    std::partial_sort(idx.begin(), idx.begin() + k, idx.end(),
                      [&](int a, int b){ return logits[a] > logits[b]; });
    std::vector<TopItem> out;
    for (int i = 0; i < k; i++) {
        int t = idx[i];
        char buf[256];
        int n = llama_token_to_piece(vocab, t, buf, sizeof(buf), 0, true);
        std::string s = n > 0 ? std::string(buf, n) : std::string();
        out.push_back({s, (float)((double)logits[t] - lse)});
    }
    return out;
}

int main(int argc, char ** argv) {
    if (argc < 2) { fprintf(stderr, "usage: warm_recall <config.json>\n"); return 2; }
    std::ifstream cf(argv[1]);
    json cfg; cf >> cfg;

    const std::string model_path = cfg["model"];
    const std::string mmproj     = cfg["mmproj"];
    const int   n_ctx       = cfg.value("n_ctx", 57344);
    const int   n_gpu_layers= cfg.value("n_gpu_layers", 99);
    const int   seed        = cfg.value("seed", 0);
    const int   n_predict   = cfg.value("n_predict", 64);
    const std::string header = cfg["header"];
    const std::string freq_path = cfg.value("gpu_freq_path", "");
    const std::string out_path  = cfg["out"];
    std::vector<std::string> frames = cfg["frames"].get<std::vector<std::string>>();

    llama_backend_init();

    // ---- load model + context (match the server stack) ----
    common_params params;
    params.model.path        = model_path;
    params.mmproj.path       = mmproj;
    params.n_ctx             = n_ctx;
    params.n_batch           = cfg.value("n_batch", 2048);   // llama.cpp / server defaults:
    params.n_ubatch          = cfg.value("n_ubatch", 512);   // match the server's FP reduction order
    params.n_gpu_layers      = n_gpu_layers;
    params.flash_attn_type   = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    params.cpuparams.n_threads = cfg.value("n_threads", 6);
    postprocess_cpu_params(params.cpuparams);
    postprocess_cpu_params(params.cpuparams_batch, &params.cpuparams);
    params.sampling.seed     = seed;
    params.sampling.temp     = 0.0f;          // greedy
    params.use_jinja         = true;          // the server runs --jinja
    params.warmup            = false;
    params.mmproj_use_gpu    = true;

    common_init_result_ptr init = common_init_from_params(params);
    llama_model   * model = init->model();
    llama_context * lctx  = init->context();
    if (!model || !lctx) { fprintf(stderr, "model load failed\n"); return 1; }
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const int n_vocab = llama_vocab_n_tokens(vocab);
    llama_memory_t mem = llama_get_memory(lctx);

    common_chat_templates_ptr tmpls = common_chat_templates_init(model, params.chat_template);

    // vision context
    mtmd_context_params mparams = mtmd_context_params_default();
    mparams.use_gpu         = true;
    mparams.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    mparams.n_threads       = params.cpuparams.n_threads;
    mparams.print_timings   = false;
    mtmd_context * mctx = mtmd_init_from_file(mmproj.c_str(), model, mparams);
    if (!mctx) { fprintf(stderr, "mmproj load failed\n"); return 1; }

    const std::string marker = mtmd_default_marker();
    const int N = (int)frames.size();

    // ---- build the formatted single user turn: header + N markers + <question> ----
    auto format_turn = [&](const std::string & qtext) -> std::string {
        common_chat_msg msg; msg.role = "user";
        std::string content = header;
        for (int i = 0; i < N; i++) content += marker;
        content += qtext;
        msg.content = content;
        std::vector<common_chat_msg> hist;   // empty -> add_bos handled by tokenizer
        return common_chat_format_single(tmpls.get(), hist, msg, /*add_ass*/ true, params.use_jinja);
    };

    // split a formatted string on the media marker into N+1 text segments
    auto split_segments = [&](const std::string & s) -> std::vector<std::string> {
        std::vector<std::string> segs; size_t start = 0, pos;
        while ((pos = s.find(marker, start)) != std::string::npos) {
            segs.push_back(s.substr(start, pos - start));
            start = pos + marker.size();
        }
        segs.push_back(s.substr(start));
        return segs;
    };

    // ---- warm the history ONCE: eval [seg0, img0, seg1, ..., seg_{N-1}, img_{N-1}] ----
    // (segments 0..N-1 and the images do not depend on the question; segment N holds it.)
    std::string fmt0 = format_turn(cfg["questions"][0]["text"].get<std::string>());
    std::vector<std::string> warm_segs = split_segments(fmt0);  // N+1 segments
    if ((int)warm_segs.size() != N + 1) {
        fprintf(stderr, "segment/marker mismatch: %zu segs, %d images\n", warm_segs.size(), N);
        return 1;
    }
    // load bitmaps
    mtmd::bitmaps bitmaps;
    mtmd_helper_init_opt iopt = mtmd_helper_init_opt_default();
    for (auto & fp : frames) {
        auto res = mtmd_helper_bitmap_init_from_file(mctx, fp.c_str(), false, iopt);
        if (!res.bitmap) { fprintf(stderr, "bitmap load failed: %s\n", fp.c_str()); return 1; }
        bitmaps.entries.emplace_back(res.bitmap);
    }
    auto bmp_cptr = bitmaps.c_ptr();
    // interleave warm parts: seg0, img0, seg1, img1, ..., seg_{N-1}, img_{N-1}  (DROP seg N)
    std::vector<mtmd_input_text> wtexts(N);
    std::vector<mtmd_input_part> wparts;
    for (int i = 0; i < N; i++) {
        wtexts[i] = { warm_segs[i].data(), warm_segs[i].size(), false, true };
        wparts.push_back({ &wtexts[i], nullptr });
        wparts.push_back({ nullptr, bmp_cptr[i] });
    }
    std::vector<const mtmd_input_part *> wparts_ptr;
    for (auto & p : wparts) wparts_ptr.push_back(&p);

    mtmd::input_chunks wchunks(mtmd_input_chunks_init());
    if (mtmd_tokenize_from_parts(mctx, wchunks.ptr.get(), wparts_ptr.data(), wparts_ptr.size(),
                                 /*add_bos*/ true) != 0) {
        fprintf(stderr, "warm tokenize failed\n"); return 1; }
    // history KV tokens (sum of chunk n_tokens) -- distinct from n_past (M-RoPE positions)
    size_t history_tokens = 0;
    {
        size_t nc = mtmd_input_chunks_size(wchunks.ptr.get());
        for (size_t i = 0; i < nc; i++)
            history_tokens += mtmd_input_chunk_get_n_tokens(mtmd_input_chunks_get(wchunks.ptr.get(), i));
    }
    bitmaps.entries.clear();

    long freq0 = read_gpu_freq(freq_path);
    auto tw = clk::now();
    llama_pos H = 0;
    if (mtmd_helper_eval_chunks(mctx, lctx, wchunks.ptr.get(), /*n_past*/ 0, /*seq*/ 0,
                                params.n_batch, /*logits_last*/ false, &H) != 0) {
        fprintf(stderr, "warm eval failed\n"); return 1; }
    double warm_s = since(tw);
    fprintf(stderr, "[warm] %d frames -> history n_past=%d in %.3fs\n", N, (int)H, warm_s);

    // ---- per-question: rewind to H, eval the question suffix, decode ----
    std::ofstream out(out_path);
    json meta = {{"type","meta"}, {"n_frames", N}, {"history_n_past", (int)H},
                 {"history_tokens", (int)history_tokens},
                 {"warm_s", warm_s}, {"n_ctx", n_ctx}, {"n_vocab", n_vocab},
                 {"flash_attn", true}, {"seed", seed}};
    out << meta.dump() << "\n"; out.flush();

    common_sampler * smpl = common_sampler_init(model, params.sampling);

    for (auto & q : cfg["questions"]) {
        std::string qid   = q["id"];
        std::string qtext = q["text"];
        std::string fmt   = format_turn(qtext);
        std::vector<std::string> segs = split_segments(fmt);
        std::string suffix = segs[N];   // question text + assistant-turn template tail

        // rewind KV to the warm history
        llama_memory_seq_rm(mem, 0, H, -1);
        common_sampler_reset(smpl);

        long fb = read_gpu_freq(freq_path);
        auto t0 = clk::now();

        // tokenize + eval ONLY the suffix (text) over the cached context
        mtmd_input_text st = { suffix.data(), suffix.size(), /*add_special*/ false, /*parse_special*/ true };
        mtmd_input_part sp = { &st, nullptr };
        const mtmd_input_part * sp_ptr = &sp;
        mtmd::input_chunks schunks(mtmd_input_chunks_init());
        if (mtmd_tokenize_from_parts(mctx, schunks.ptr.get(), &sp_ptr, 1, /*add_bos*/ false) != 0) {
            fprintf(stderr, "suffix tokenize failed (%s)\n", qid.c_str()); return 1; }
        size_t nsc = mtmd_input_chunks_size(schunks.ptr.get());
        auto schunk = mtmd_input_chunks_get(schunks.ptr.get(), nsc - 1);
        int n_suffix = (int)mtmd_input_chunk_get_n_tokens(schunk);

        llama_pos new_np = H;
        if (mtmd_helper_eval_chunk_single(mctx, lctx, schunk, H, 0, params.n_batch,
                                          /*logits_last*/ true, &new_np) != 0) {
            fprintf(stderr, "suffix eval failed (%s)\n", qid.c_str()); return 1; }

        // first token: top-20 logprobs from the suffix-eval logits, then greedy sample
        const float * logits = llama_get_logits_ith(lctx, -1);
        std::vector<TopItem> top = topk_logprobs(logits, n_vocab, vocab, 20);
        llama_token first = common_sampler_sample(smpl, lctx, -1);
        common_sampler_accept(smpl, first, true);
        double ttft = since(t0);

        // continue decoding the answer
        std::string answer;
        char pbuf[256];
        int np = llama_token_to_piece(vocab, first, pbuf, sizeof(pbuf), 0, true);
        if (np > 0) answer.append(pbuf, np);
        int n_gen = 1;
        llama_pos pos = new_np;
        common_batch batch(lctx);
        llama_token cur = first;
        while (n_gen < n_predict && !llama_vocab_is_eog(vocab, cur)) {
            batch.clear();
            batch.add(cur, pos++, 0, true);
            if (llama_process(lctx, LLAMA_PROCESS_TYPE_DECODE, batch.get())) break;
            cur = common_sampler_sample(smpl, lctx, -1);
            common_sampler_accept(smpl, cur, true);
            if (llama_vocab_is_eog(vocab, cur)) break;
            int m = llama_token_to_piece(vocab, cur, pbuf, sizeof(pbuf), 0, true);
            if (m > 0) answer.append(pbuf, m);
            n_gen++;
        }
        double total = since(t0);
        long fa = read_gpu_freq(freq_path);

        json top_j = json::array();
        for (auto & t : top) top_j.push_back({ t.tok, t.logprob });
        std::string first_tok;
        { int n = llama_token_to_piece(vocab, first, pbuf, sizeof(pbuf), 0, true);
          if (n > 0) first_tok.assign(pbuf, n); }
        json row = {
            {"question_id", qid}, {"history_n_past", (int)H}, {"n_suffix_tokens", n_suffix},
            {"ttft_s", ttft}, {"total_s", total}, {"n_gen", n_gen},
            {"first_token", first_tok}, {"answer_text", answer.substr(0, 80)},
            {"top20", top_j},
            {"gpu_freq_before", fb}, {"gpu_freq_after", fa}
        };
        out << row.dump() << "\n"; out.flush();
        fprintf(stderr, "[q] %s ttft=%.3fs total=%.3fs nsuf=%d ngen=%d ans='%s'\n",
                qid.c_str(), ttft, total, n_suffix, n_gen, answer.substr(0, 24).c_str());
    }

    common_sampler_free(smpl);
    mtmd_free(mctx);
    llama_backend_free();
    (void)freq0;
    return 0;
}
