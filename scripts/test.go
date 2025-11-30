package main

import (
    "fmt"
    "math/rand"
    "time"
)

func addIntegers(numbers []int) int {
    sum := 0
    for _, num := range numbers {
        sum += num
    }
    return sum
}

func generateRandomNumbers(count int) []int {
    rand.Seed(time.Now().UnixNano())
    numbers := make([]int, count)
    for i := 0; i < count; i++ {
        numbers[i] = rand.Intn(100) + 1
    }
    return numbers
}

func main() {
    const numIterations = 1000000
    const numbersPerIteration = 100
    
    fmt.Println("Starting integer addition benchmark...")
    
    totalSum := int64(0)
    
    for i := 0; i < numIterations; i++ {
        numbers := generateRandomNumbers(numbersPerIteration)
        sum := addIntegers(numbers)
        totalSum += int64(sum)
        
        if i%100000 == 0 {
            fmt.Printf("Progress: %d/%d\n", i, numIterations)
        }
    }
    
    fmt.Println("Completed!")
    fmt.Printf("Total sum across all iterations: %d\n", totalSum)
}