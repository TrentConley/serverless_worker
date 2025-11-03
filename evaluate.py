#!/usr/bin/env python3
"""
Chess Model Evaluator

Runs participant's predict() function on test dataset and calculates metrics
"""
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Any


def extract_piece_positions(fen: str) -> str:
    """
    Extract only piece positions from FEN string
    
    Args:
        fen: Full or partial FEN string
    
    Returns:
        Piece positions only (first field)
    """
    # Handle both full FEN and piece-positions-only
    return fen.split()[0] if ' ' in fen else fen


def compare_positions(predicted: str, ground_truth: str) -> bool:
    """
    Compare two FEN strings based on piece positions only
    
    Args:
        predicted: Predicted FEN (may be full or partial)
        ground_truth: Ground truth FEN (may be full or partial)
    
    Returns:
        True if piece positions match exactly
    """
    pred_pos = extract_piece_positions(predicted.strip())
    gt_pos = extract_piece_positions(ground_truth.strip())
    return pred_pos == gt_pos


def calculate_piece_accuracy(predicted: str, ground_truth: str) -> float:
    """
    Calculate per-piece accuracy (for partial credit analysis)
    
    Args:
        predicted: Predicted FEN piece positions
        ground_truth: Ground truth FEN piece positions
    
    Returns:
        Fraction of squares that match (0.0 to 1.0)
    """
    pred_pos = extract_piece_positions(predicted.strip())
    gt_pos = extract_piece_positions(ground_truth.strip())
    
    # Convert to board representation (64 squares)
    pred_board = fen_to_board(pred_pos)
    gt_board = fen_to_board(gt_pos)
    
    # Count matching squares
    matches = sum(1 for p, g in zip(pred_board, gt_board) if p == g)
    return matches / 64.0


def fen_to_board(fen_pos: str) -> List[str]:
    """
    Convert FEN piece positions to 64-element list
    
    Args:
        fen_pos: FEN piece positions string
    
    Returns:
        List of 64 strings (piece or empty)
    """
    board = []
    ranks = fen_pos.split('/')
    
    for rank in ranks:
        for char in rank:
            if char.isdigit():
                board.extend(['.'] * int(char))
            else:
                board.append(char)
    
    return board


def evaluate_submission(
    test_dir: str,
    predict_func,
    max_samples: int = None
) -> Dict[str, Any]:
    """
    Evaluate a submission's predict function on test dataset
    
    Args:
        test_dir: Path to test dataset directory
        predict_func: Function with signature: predict(image_path: str) -> str
        max_samples: Maximum number of samples to evaluate (None = all)
    
    Returns:
        Dictionary with evaluation results and metrics
    """
    test_path = Path(test_dir)
    images_dir = test_path / "images"
    labels_dir = test_path / "labels"
    
    # Get all test images (skip macOS metadata files)
    image_files = sorted([p for p in images_dir.glob("*.png") if not p.name.startswith('._')])
    
    if max_samples:
        image_files = image_files[:max_samples]
    
    results = {
        "predictions": [],
        "timing": [],
        "metrics": {}
    }
    
    print(f"Evaluating on {len(image_files)} images...")
    
    # Test predict function first
    try:
        test_result = predict_func(str(image_files[0]))
        print(f"Test prediction type: {type(test_result)}, length: {len(str(test_result)) if test_result else 0}")
        print(f"Test prediction value: {test_result[:100] if test_result else 'None/Empty'}")
    except Exception as e:
        print(f"WARNING: Test prediction failed: {e}")
    
    # Evaluate each image
    for idx, img_path in enumerate(image_files):
        # Load ground truth
        label_path = labels_dir / f"{img_path.stem}.txt"
        
        if not label_path.exists():
            print(f"Warning: Missing label for {img_path.name}")
            continue
        
        # Read ground truth (skip if it's corrupted/metadata)
        try:
            ground_truth = label_path.read_text().strip()
        except UnicodeDecodeError:
            print(f"Warning: Skipping corrupted label file: {label_path.name}")
            continue
        
        # Run prediction with timing
        try:
            start_time = time.time()
            predicted = predict_func(str(img_path))
            elapsed = time.time() - start_time
            
            # Validate output
            if not predicted or not isinstance(predicted, str):
                print(f"Warning: {img_path.name} returned invalid output: {type(predicted)}")
                results["predictions"].append({
                    "image": img_path.name,
                    "error": f"Invalid output type: {type(predicted)}",
                    "correct": False,
                    "piece_accuracy": 0.0,
                    "time_seconds": elapsed
                })
                results["timing"].append(elapsed)
                continue
                
        except Exception as e:
            print(f"Error predicting {img_path.name}: {e}")
            import traceback
            traceback.print_exc()
            results["predictions"].append({
                "image": img_path.name,
                "error": str(e),
                "correct": False,
                "piece_accuracy": 0.0,
                "time_seconds": 0.0
            })
            continue
        
        # Compare results
        correct = compare_positions(predicted, ground_truth)
        piece_acc = calculate_piece_accuracy(predicted, ground_truth)
        
        results["predictions"].append({
            "image": img_path.name,
            "predicted": extract_piece_positions(predicted),
            "ground_truth": extract_piece_positions(ground_truth),
            "correct": correct,
            "piece_accuracy": piece_acc,
            "time_seconds": elapsed
        })
        
        results["timing"].append(elapsed)
        
        # Show first 3 predictions for debugging
        if idx < 3:
            print(f"\n  Sample {idx + 1}: {img_path.name}")
            print(f"    Predicted: {extract_piece_positions(predicted)[:50]}...")
            print(f"    Truth:     {extract_piece_positions(ground_truth)[:50]}...")
            print(f"    Piece Acc: {piece_acc:.2%}")
        
        # Progress
        if (idx + 1) % 100 == 0:
            correct_so_far = sum(1 for p in results["predictions"] if p.get("correct", False))
            acc_so_far = correct_so_far / len(results["predictions"])
            avg_piece_acc_so_far = sum(p.get("piece_accuracy", 0) for p in results["predictions"]) / len(results["predictions"])
            print(f"  {idx + 1}/{len(image_files)} - Accuracy: {acc_so_far:.2%}, Avg Piece Acc: {avg_piece_acc_so_far:.2%}")
    
    # Calculate final metrics
    total = len(results["predictions"])
    correct_count = sum(1 for p in results["predictions"] if p.get("correct", False))
    
    results["metrics"] = {
        "total_images": total,
        "correct_predictions": correct_count,
        "accuracy": correct_count / total if total > 0 else 0.0,
        "avg_inference_time": sum(results["timing"]) / len(results["timing"]) if results["timing"] else 0.0,
        "total_time": sum(results["timing"]),
        "avg_piece_accuracy": sum(p.get("piece_accuracy", 0) for p in results["predictions"]) / total if total > 0 else 0.0
    }
    
    return results


def save_results(results: Dict[str, Any], output_path: str):
    """Save evaluation results to JSON file"""
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")


def print_summary(results: Dict[str, Any]):
    """Print evaluation summary"""
    metrics = results["metrics"]
    
    print("\n" + "="*60)
    print("EVALUATION SUMMARY")
    print("="*60)
    print(f"Total Images:          {metrics['total_images']}")
    print(f"Correct Predictions:   {metrics['correct_predictions']}")
    print(f"Accuracy:              {metrics['accuracy']:.2%}")
    print(f"Avg Piece Accuracy:    {metrics['avg_piece_accuracy']:.2%}")
    print(f"Avg Inference Time:    {metrics['avg_inference_time']:.4f} seconds")
    print(f"Total Time:            {metrics['total_time']:.2f} seconds")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate chess position prediction model")
    parser.add_argument("submission_dir", help="Path to submission directory containing predict.py")
    parser.add_argument("test_dir", help="Path to test dataset directory")
    parser.add_argument("-n", "--max-samples", type=int, help="Max samples to evaluate (default: all)")
    parser.add_argument("-o", "--output", default="results.json", help="Output JSON file")
    
    args = parser.parse_args()
    
    # Import predict function from submission
    sys.path.insert(0, args.submission_dir)
    from predict import predict
    
    # Run evaluation
    results = evaluate_submission(
        args.test_dir,
        predict,
        args.max_samples
    )
    
    # Print and save results
    print_summary(results)
    save_results(results, args.output)
