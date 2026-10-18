// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Accolades/LyraAccoladeDefinition.h"
#include "AsyncMixin.h"
#include "CommonUserWidget.h"

#include "LyraAccoladeHostWidget.generated.h"

class UObject;
class USoundBase;
class UUserWidget;

USTRUCT(BlueprintType)
struct FPendingAccoladeEntry
{
	GENERATED_BODY();

	UPROPERTY(BlueprintReadOnly)
	FLyraAccoladeDefinitionRow Row; 

	UPROPERTY(BlueprintReadOnly)
	TObjectPtr<USoundBase> Sound = nullptr;

	UPROPERTY(BlueprintReadOnly)
	TObjectPtr<UObject> Icon = nullptr;

	UPROPERTY()
	TObjectPtr<UUserWidget> AllocatedWidget = nullptr;
};

/**
 * 
 */
UCLASS(BlueprintType)
class ULyraAccoladeHostWidget : public UCommonUserWidget, public FAsyncMixin
{
	GENERATED_BODY()

public:
	// The location tag (used to filter incoming messages to only display the appropriate accolades in a given location)
	UPROPERTY(EditAnywhere, BlueprintReadOnly)
	FGameplayTag LocationName;

	//~UUserWidget interface
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	//~End of UUserWidget interface

	UFUNCTION(BlueprintImplementableEvent)
	void DestroyAccoladeWidget(UUserWidget* Widget);

	UFUNCTION(BlueprintImplementableEvent)
	UUserWidget* CreateAccoladeWidget(const FPendingAccoladeEntry& Entry);

	// Runtime behavior and state are intentionally absent from this benchmark starter.
};
