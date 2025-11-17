#include <iostream>
#include <vector>
#include <random>

// Simple function to add integers together
int addIntegers(const std::vector<int>& numbers) {
    int sum = 0;
    for (int num : numbers) {
        sum += num;
    }
    return sum;
}

// Function to generate random integers
std::vector<int> generateRandomNumbers(int count) {
    std::vector<int> numbers;
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(1, 100);
    
    for (int i = 0; i < count; ++i) {
        numbers.push_back(dis(gen));
    }
    return numbers;
}

int main() {
    // Generate a large number of integers to make profiling meaningful
    const int NUM_ITERATIONS = 1000000;
    const int NUMBERS_PER_ITERATION = 100;
    
    std::cout << "Starting integer addition benchmark..." << std::endl;
    
    long long totalSum = 0;
    
    // Perform many iterations to generate meaningful profile data
    for (int i = 0; i < NUM_ITERATIONS; ++i) {
        std::vector<int> numbers = generateRandomNumbers(NUMBERS_PER_ITERATION);
        int sum = addIntegers(numbers);
        totalSum += sum;
        
        // Print progress occasionally
        if (i % 100000 == 0) {
            std::cout << "Progress: " << i << "/" << NUM_ITERATIONS << std::endl;
        }
    }
    
    std::cout << "Completed!" << std::endl;
    std::cout << "Total sum across all iterations: " << totalSum << std::endl;
    
    return 0;
}
