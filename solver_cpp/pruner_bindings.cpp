/**
 * pruner_bindings.cpp — Fast C++ pruning operations for NeuralGTO
 *
 * Provides pybind11 bindings for performance-critical solver operations:
 * - JSON parsing and action frequency extraction
 * - Action name normalization
 * - Convergence checking
 *
 * Created: 2026-03-03
 * Task: T4.2c
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>
#include <cmath>
#include <algorithm>
#include <stdexcept>

// Use nlohmann/json (same as TexasSolver)
#include "../../TexasSolver/include/json.hpp"

namespace py = pybind11;
using json = nlohmann::json;

/**
 * Extract action frequencies from solver JSON output.
 * 
 * Parses the root action node's strategy and computes average frequency
 * of each action across all hand combos.
 *
 * @param json_path Path to solver output JSON file
 * @return Map of action names to average frequencies
 * @throws std::runtime_error if file cannot be read or parsed
 */
std::unordered_map<std::string, double> extract_action_frequencies(
    const std::string& json_path
) {
    // Load JSON from file
    std::ifstream file(json_path);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open JSON file: " + json_path);
    }

    json tree;
    try {
        file >> tree;
    } catch (const json::exception& e) {
        throw std::runtime_error(std::string("JSON parse error: ") + e.what());
    }

    // Find root action node (recursively search for node with "actions" field)
    std::function<json*(json&)> find_root = [&](json& node) -> json* {
        if (node.contains("actions") && node["actions"].is_array() && 
            !node["actions"].empty()) {
            return &node;
        }
        if (node.contains("children") && node["children"].is_array()) {
            for (auto& child : node["children"]) {
                json* result = find_root(child);
                if (result != nullptr) return result;
            }
        }
        return nullptr;
    };

    json* root = find_root(tree);
    if (root == nullptr) {
        throw std::runtime_error("No action node found in output JSON");
    }

    // Extract actions list and strategy data
    if (!root->contains("actions") || !root->contains("strategy")) {
        throw std::runtime_error("Missing actions or strategy in root node");
    }

    const auto& actions = (*root)["actions"];
    const auto& strategy_wrapper = (*root)["strategy"];
    
    if (!strategy_wrapper.contains("strategy")) {
        throw std::runtime_error("Missing nested strategy field");
    }
    
    const auto& strategy_data = strategy_wrapper["strategy"];

    if (actions.empty() || strategy_data.empty()) {
        throw std::runtime_error("Empty actions or strategy data");
    }

    size_t n_actions = actions.size();
    std::vector<double> totals(n_actions, 0.0);
    size_t count = 0;

    // Sum frequencies across all hands
    for (auto& [hand, freqs] : strategy_data.items()) {
        if (!freqs.is_array()) continue;
        
        for (size_t i = 0; i < std::min(n_actions, freqs.size()); ++i) {
            totals[i] += freqs[i].get<double>();
        }
        ++count;
    }

    if (count == 0) {
        throw std::runtime_error("No hands found in strategy data");
    }

    // Compute averages
    std::unordered_map<std::string, double> result;
    for (size_t i = 0; i < n_actions; ++i) {
        std::string action_name = actions[i].get<std::string>();
        result[action_name] = std::round(totals[i] / count * 10000.0) / 10000.0;
    }

    return result;
}

/**
 * Normalize action names from chip amounts to percentages.
 *
 * Converts solver output names like "BET 16.500000" to "BET 33" by
 * matching chip amounts to the nearest configured bet size percentage.
 *
 * @param frequencies Map of raw action names to frequencies
 * @param pot_size_bb Pot size in big blinds
 * @param effective_stack_bb Effective stack in big blinds
 * @param bet_sizes_pct List of bet size percentages (e.g., [33, 75])
 * @return Map of normalized action names to frequencies
 */
std::unordered_map<std::string, double> normalize_action_names(
    const std::unordered_map<std::string, double>& frequencies,
    double pot_size_bb,
    double effective_stack_bb,
    const std::vector<int>& bet_sizes_pct
) {
    std::unordered_map<std::string, double> result;

    for (const auto& [action, freq] : frequencies) {
        std::string normalized = action;
        
        // Parse action format: "BET 16.500000" or "RAISE 32.500000"
        if (action.rfind("BET ", 0) == 0 || action.rfind("RAISE ", 0) == 0) {
            size_t space_pos = action.find(' ');
            if (space_pos != std::string::npos) {
                std::string action_type = action.substr(0, space_pos);
                std::string amount_str = action.substr(space_pos + 1);
                
                try {
                    double value = std::stod(amount_str);
                    
                    // Heuristic to detect if value is already a percentage:
                    // 1. If value < 10, it's almost certainly a chip amount (no one bets <10% pot)
                    // 2. If value >= 10 AND matches a configured bet size within 5%, it's a percentage
                    // 3. Otherwise, treat as chip amount
                    bool is_percentage = false;
                    if (value >= 10.0 && !bet_sizes_pct.empty()) {
                        for (int size : bet_sizes_pct) {
                            if (std::abs(value - size) < 5.0) {
                                is_percentage = true;
                                break;
                            }
                        }
                    }
                    
                    if (!is_percentage) {
                        // Convert chip amount to pot percentage
                        double pot_pct = (value / pot_size_bb) * 100.0;
                        
                        // Match to nearest configured bet size
                        if (!bet_sizes_pct.empty()) {
                            int nearest = bet_sizes_pct[0];
                            double min_diff = std::abs(pot_pct - nearest);
                            
                            for (int size : bet_sizes_pct) {
                                double diff = std::abs(pot_pct - size);
                                if (diff < min_diff) {
                                    min_diff = diff;
                                    nearest = size;
                                }
                            }
                            
                            normalized = action_type + " " + std::to_string(nearest);
                        } else {
                            // No bet sizes provided — just round
                            normalized = action_type + " " + std::to_string(
                                static_cast<int>(std::round(pot_pct))
                            );
                        }
                    }
                    // else: already a percentage, keep original
                } catch (const std::exception&) {
                    // Keep original if parsing fails
                }
            }
        }
        
        result[normalized] = freq;
    }

    return result;
}

/**
 * Check if action frequency bounds have converged.
 *
 * Computes standard deviation of action frequencies and returns true
 * if it's below the threshold, indicating convergence.
 *
 * @param frequencies Map of action names to frequencies
 * @param threshold Convergence threshold (default: 0.01 = 1%)
 * @return true if converged, false otherwise
 */
bool check_convergence(
    const std::unordered_map<std::string, double>& frequencies,
    double threshold = 0.01
) {
    if (frequencies.empty()) return false;

    // Compute mean
    double sum = 0.0;
    for (const auto& [action, freq] : frequencies) {
        sum += freq;
    }
    double mean = sum / frequencies.size();

    // Compute standard deviation
    double variance = 0.0;
    for (const auto& [action, freq] : frequencies) {
        double diff = freq - mean;
        variance += diff * diff;
    }
    double stdev = std::sqrt(variance / frequencies.size());

    return stdev < threshold;
}

/**
 * Extract and normalize action frequencies in one call.
 *
 * Convenience function that combines extract_action_frequencies and
 * normalize_action_names for efficiency.
 *
 * @param json_path Path to solver output JSON
 * @param pot_size_bb Pot size in big blinds
 * @param effective_stack_bb Effective stack in big blinds
 * @param bet_sizes_pct List of bet size percentages
 * @return Map of normalized action names to frequencies
 */
std::unordered_map<std::string, double> extract_and_normalize(
    const std::string& json_path,
    double pot_size_bb,
    double effective_stack_bb,
    const std::vector<int>& bet_sizes_pct
) {
    auto raw_freqs = extract_action_frequencies(json_path);
    return normalize_action_names(raw_freqs, pot_size_bb, effective_stack_bb, bet_sizes_pct);
}

// Pybind11 module definition
PYBIND11_MODULE(_solver_pruner_cpp, m) {
    m.doc() = "Fast C++ pruning operations for NeuralGTO (T4.2c)";

    m.def("extract_action_frequencies", &extract_action_frequencies,
          py::arg("json_path"),
          "Extract action frequencies from solver JSON output");

    m.def("normalize_action_names", &normalize_action_names,
          py::arg("frequencies"),
          py::arg("pot_size_bb"),
          py::arg("effective_stack_bb"),
          py::arg("bet_sizes_pct"),
          "Normalize action names from chip amounts to percentages");

    m.def("check_convergence", &check_convergence,
          py::arg("frequencies"),
          py::arg("threshold") = 0.01,
          "Check if action frequencies have converged");

    m.def("extract_and_normalize", &extract_and_normalize,
          py::arg("json_path"),
          py::arg("pot_size_bb"),
          py::arg("effective_stack_bb"),
          py::arg("bet_sizes_pct"),
          "Extract and normalize action frequencies in one call");
}
